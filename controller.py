import asyncio
import struct
from contextlib import suppress

import httpx       # 「頭」サーバー (LLM) との接続用
import websockets  # 「耳」サーバー (STT) との接続用

try:
    import pyaudio
except ModuleNotFoundError as exc:  # pragma: no cover - guidance for manual setup
    raise ModuleNotFoundError(
        "PyAudio が見つかりませんでした。'pip install pyaudio' を実行し、"
        "Homebrew なら 'brew install portaudio' を先に入れてください。"
    ) from exc

# --- 各サーバーのアドレス ---
EARS_STT_SERVER_URL = "ws://127.0.0.1:8001/listen"
HEAD_LLM_SERVER_URL = "http://127.0.0.1:8002/think"
MOUTH_TTS_SERVER_URL = "http://127.0.0.1:8003/speak"

_pyaudio = pyaudio.PyAudio()


async def _play_tts(text: str) -> None:
    """口（TTS）サーバーにテキストを送信し、返ってきた音声をスピーカーに再生する。"""

    def _play_tts_blocking(payload: str) -> None:
        pa_stream = None
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream("POST", MOUTH_TTS_SERVER_URL, json={"text": payload}) as response:
                    if response.status_code != 200:
                        body = ""
                        with suppress(Exception):
                            body = response.text
                        print(f"🛑 [Mouth] Error: Status {response.status_code} {body}")
                        return

                    header_buffer = b""
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue

                        if pa_stream is None:
                            header_buffer += chunk
                            if len(header_buffer) < 44:
                                continue

                            header = header_buffer[:44]
                            audio_payload = header_buffer[44:]

                            channels = struct.unpack_from("<H", header, 22)[0]
                            sample_rate = struct.unpack_from("<I", header, 24)[0]
                            bits_per_sample = struct.unpack_from("<H", header, 34)[0]
                            sample_width = max(bits_per_sample // 8, 1)

                            try:
                                pa_format = _pyaudio.get_format_from_width(sample_width, unsigned=False)
                            except ValueError:
                                print(f"🛑 [Mouth] Unsupported sample width: {sample_width} bytes")
                                return

                            pa_stream = _pyaudio.open(
                                format=pa_format,
                                channels=channels,
                                rate=sample_rate,
                                output=True,
                            )

                            if audio_payload:
                                pa_stream.write(audio_payload)
                            continue

                        pa_stream.write(chunk)

        except Exception as exc:
            print(f"🛑 [Mouth] Error during playback: {exc}")
        finally:
            if pa_stream is not None:
                with suppress(Exception):
                    pa_stream.stop_stream()
                with suppress(Exception):
                    pa_stream.close()

    if not text.strip():
        return

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _play_tts_blocking, text)


async def handle_llm_response(text: str):
    """
    頭（LLM）サーバーにテキストを送信し、
    ストリーミングで回答を受け取る
    """
    try:
        # 非同期HTTPクライアントを使用
        async with httpx.AsyncClient(timeout=None) as client:
            print(f"🧠 [Head] -> 送信中: '{text}'")
            
            # /think エンドポイントにJSON形式でテキストをPOST
            # httpxはストリーミングリクエストをサポート
            async with client.stream("POST", HEAD_LLM_SERVER_URL, json={"text": text}) as response:
                
                # HTTPステータスコードをチェック
                if response.status_code != 200:
                    print(f"🛑 [Head] Error: サーバーからエラーが返されました (Status: {response.status_code})")
                    return

                print("🧠 [Head] <- 回答受信中: ", end="", flush=True)
                
                full_answer = []

                # レスポンスをチャンク（断片）ごとに非同期で受信
                async for chunk in response.aiter_text():
                    if not chunk:
                        continue
                    print(chunk, end="", flush=True)
                    full_answer.append(chunk)

                print("\n")  # 回答の最後に改行

                answer_text = "".join(full_answer).strip()
                if answer_text:
                    await _play_tts(answer_text)

    except httpx.ConnectError as e:
        print(f"🛑 [Head] Error: LLMサーバー ({HEAD_LLM_SERVER_URL}) に接続できません。")
        print("    サーバーが起動しているか確認してください。")
    except Exception as e:
        print(f"🛑 [Head] Error: {e}")


async def run_controller():
    """
    メインのコントローラー
    耳（STT）サーバーに接続し、テキストを待機する
    """
    print("🚀 コントローラーを起動します...")
    print(f"👂 [Ears] STTサーバー ({EARS_STT_SERVER_URL}) に接続中...")
    
    try:
        async with websockets.connect(EARS_STT_SERVER_URL) as websocket:
            print("👂 [Ears] 接続成功。音声を待機中...")
            
            # 「耳」サーバーからテキストメッセージが送られてくるのを無限に待つ
            async for stt_text in websocket:
                print(f"\n👂 [Ears] <- 受信: '{stt_text}'")
                
                # 受け取ったテキストをLLMに渡す
                await handle_llm_response(stt_text)

    except websockets.exceptions.ConnectionClosedError:
        print(f"🛑 [Ears] サーバーとの接続が切れました。")
    except ConnectionRefusedError:
        print(f"🛑 [Ears] Error: STTサーバー ({EARS_STT_SERVER_URL}) に接続できません。")
        print("    サーバーが起動しているか確認してください。")
    except Exception as e:
        print(f"🛑 コントローラーエラー: {e}")

# --- スクリプトの実行 ---
if __name__ == "__main__":
    try:
        asyncio.run(run_controller())
    except KeyboardInterrupt:
        print("\n🛑 コントローラーを終了します。")
    finally:
        with suppress(Exception):
            _pyaudio.terminate()
