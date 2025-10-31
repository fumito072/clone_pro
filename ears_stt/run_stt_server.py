import asyncio
import collections
import threading
import time

import numpy as np
import torch
import websockets
import webrtcvad
from faster_whisper import WhisperModel
from websockets.server import WebSocketServerProtocol

try:
    import pyaudio
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "PyAudio が見つかりませんでした。'pip install pyaudio' を実行し、"
        "Homebrew を使っている場合は先に 'brew install portaudio' を入れてください。"
    ) from exc

# --- Configuration ---
MODEL_NAME = "medium"      # "tiny", "base", "small", "medium", "large-v3"
LANGUAGE = "ja"         # Japanese
SILENCE_THRESHOLD_MS = 100 # Stop transcribing after this much silence (in ms)
VAD_AGGRESSIVENESS = 3  # How aggressive VAD is (0-3). 3 is most aggressive.
SAMPLE_RATE = 16000     # Whisper requires 16kHz
CHUNK_DURATION_MS = 30  # VAD requires 10, 20, or 30 ms chunks
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
CHUNK_BYTES = CHUNK_SAMPLES * 2  # 16-bit audio
FORMAT = pyaudio.paInt16
CHANNELS = 1
ENERGY_RMS_THRESHOLD = 0.008  # Fallback sensitivity for quiet environments

# Calculate how many audio chunks fit in our silence threshold
SILENCE_CHUNKS = int(SILENCE_THRESHOLD_MS / CHUNK_DURATION_MS)

connected_clients: set[WebSocketServerProtocol] = set()


async def websocket_handler(websocket: WebSocketServerProtocol):
    path = getattr(websocket, "path", "/")
    if path != "/listen":
        print(f"⚠️ [WS] /listen 以外のパスから接続されました: {path} @ {websocket.remote_address}")
    """
    /listen に接続したクライアント（コントローラー等）を登録し、
    接続が切れるまで待機する。
    """
    connected_clients.add(websocket)
    print(f"🔌 [WS] 接続: {websocket.remote_address}")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"🔌 [WS] 切断: {websocket.remote_address}")


async def broadcast_text(text: str):
    """
    現在接続中の全クライアントに文字列を送信する。
    """
    if not connected_clients:
        return

    disconnected = []
    for ws in list(connected_clients):
        try:
            await ws.send(text)
        except Exception as exc:
            print(f"⚠️ [WS] 送信失敗: {exc}")
            disconnected.append(ws)

    for ws in disconnected:
        connected_clients.discard(ws)


def transcription_worker(loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
    print("Loading VAD (Voice Activity Detection)...")
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    print(f"Loading faster-whisper model '{MODEL_NAME}' for language '{LANGUAGE}'...")
    # Use GPU if available (MPS on Mac), otherwise CPU
    device_type = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device_type}")
    model = WhisperModel(
        MODEL_NAME,
        device=device_type,
        compute_type="float16" if device_type == "cuda" else "float32",
    )
    # --- Set up microphone stream ---
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SAMPLES)

    print("\n🎤 Listening... (Speak, then pause for transcription. Ctrl+C to stop)")
    
    frames_buffer = collections.deque()
    silence_counter = 0
    is_speaking = False

    def is_speech(chunk: bytes) -> bool:
        if vad.is_speech(chunk, SAMPLE_RATE):
            return True

        # Fallback: simple RMS energy check
        audio = np.frombuffer(chunk, dtype=np.int16)
        if audio.size == 0:
            return False
        rms = np.sqrt(np.mean((audio.astype(np.float32) / 32768.0) ** 2))
        return rms > ENERGY_RMS_THRESHOLD

    try:
        while not stop_event.is_set():
            try:
                chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
            except OSError as err:
                if err.errno == -9981:
                    print("⚠️ Input overflow detected, skipping chunk...")
                    time.sleep(0.01)
                    continue
                raise

            if stop_event.is_set():
                break
            
            # 1. Detect if this chunk is speech
            is_speech_chunk = is_speech(chunk)

            if is_speaking:
                if is_speech_chunk:
                    # Still speaking, keep recording
                    frames_buffer.append(chunk)
                    silence_counter = 0
                else:
                    # Was speaking, but now silent
                    silence_counter += 1
                    if silence_counter >= SILENCE_CHUNKS:
                        # Reached silence threshold, time to transcribe
                        print("Silence detected, transcribing...")
                        
                        # --- Transcribe the buffer ---
                        audio_data = np.frombuffer(b''.join(frames_buffer), dtype=np.int16)
                        audio_float = audio_data.astype(np.float32) / 32768.0
                        
                        segments, info = model.transcribe(audio_float, language=LANGUAGE, temperature=0)
                        
                        full_text = "".join(segment.text for segment in segments)
                        print(f"==> [STT]: {full_text}\n")

                        if full_text:
                            asyncio.run_coroutine_threadsafe(
                                broadcast_text(full_text),
                                loop,
                            )
                        
                        # Reset
                        frames_buffer.clear()
                        silence_counter = 0
                        is_speaking = False
            
            elif is_speech_chunk:
                # Just started speaking
                print("Speech detected...")
                is_speaking = True
                frames_buffer.append(chunk)
                silence_counter = 0

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except Exception as exc:
        print(f"\n🛑 STT Error: {exc}")
    finally:
        # Clean up
        try:
            if stream.is_active():
                stream.stop_stream()
        except OSError:
            pass
        stream.close()
        p.terminate()
        print("Done.")


async def async_main():
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    server = await websockets.serve(websocket_handler, host="0.0.0.0", port=8001)
    print("🔌 WebSocketサーバーを起動しました: ws://0.0.0.0:8001/listen")

    worker = threading.Thread(
        target=transcription_worker,
        args=(loop, stop_event),
        daemon=True,
    )
    worker.start()

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()
        server.close()
        await server.wait_closed()
        await asyncio.to_thread(worker.join)
        for ws in list(connected_clients):
            try:
                await ws.close()
            except Exception:
                pass
        connected_clients.clear()


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
