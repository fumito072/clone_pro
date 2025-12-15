import asyncio
import os
import threading
import queue
import time
import audioop
from pathlib import Path
from google.cloud import speech
from google.oauth2 import service_account
import pyaudio
import websockets
from websockets.server import WebSocketServerProtocol

# --- Google Cloud 認証情報の設定 ---
# Application Default Credentials (ADC) を優先使用
# gcloud auth application-default login で認証済みの場合は自動的に使用されます
CREDENTIALS_PATH = Path(__file__).parent / "google_credentials.json"

# JSONファイルがある場合のみ使用、なければADCを使用
if CREDENTIALS_PATH.exists() and CREDENTIALS_PATH.stat().st_size > 0:
    try:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(CREDENTIALS_PATH)
        print(f"✅ 認証情報ファイルを使用: {CREDENTIALS_PATH}")
    except Exception as e:
        print(f"⚠️  認証情報ファイルの読み込みに失敗: {e}")
        print("ℹ️  Application Default Credentials (ADC) にフォールバック")
        if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
            del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
else:
    print("ℹ️  Application Default Credentials (ADC) を使用します")
    print("   ※ gcloud auth application-default login で認証済みであることを確認してください")
    # 環境変数をクリア（ADCを使うため）
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

# --- 音声設定 ---
RATE = 16000  # Google Speech-to-Textの推奨サンプリングレート
CHUNK = int(RATE / 10)  # 100ms
FORMAT = pyaudio.paInt16
CHANNELS = 1

# --- WebSocketクライアント管理 ---
connected_clients: set[WebSocketServerProtocol] = set()
listening_event = threading.Event()
listening_event.set()  # 初期状態はリスニング中


async def websocket_handler(websocket: WebSocketServerProtocol):
    """
    /listen に接続したクライアント（コントローラー等）を登録し、
    接続が切れるまで待機する。
    """
    path = getattr(websocket, "path", "/")
    if path != "/listen":
        print(f"⚠️  [WS] /listen 以外のパスから接続されました: {path} @ {websocket.remote_address}")
    
    connected_clients.add(websocket)
    print(f"🔌 [WS] 接続: {websocket.remote_address}")
    
    try:
        # 接続確認メッセージ
        await websocket.send("ACK: Connected to STT Server")
        await websocket.send("STATE: LISTENING")
        
        async for message in websocket:
            if not isinstance(message, str):
                continue
            
            command = message.strip().upper()
            
            if command == "PAUSE_LISTENING":
                if listening_event.is_set():
                    print("⏸️  [WS] Listening paused by controller.")
                    listening_event.clear()
                    await websocket.send("STATE: PAUSED")
            
            elif command == "RESUME_LISTENING":
                if not listening_event.is_set():
                    print("▶️  [WS] Listening resumed by controller.")
                    listening_event.set()
                    await websocket.send("STATE: LISTENING")
            
            else:
                print(f"ℹ️  [WS] 未対応のメッセージを受信: {message}")
    
    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 [WS] 接続が切断されました: {websocket.remote_address}")
    finally:
        connected_clients.discard(websocket)
        print(f"🔌 [WS] 切断完了: {websocket.remote_address}")


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
            print(f"📤 [WS] 送信: '{text}' → {ws.remote_address}")
        except Exception as exc:
            print(f"⚠️  [WS] 送信失敗: {exc}")
            disconnected.append(ws)

    for ws in disconnected:
        connected_clients.discard(ws)


class SpeechToTextEngine:
    """Google Cloud Speech-to-Text APIを使った音声認識エンジン"""
    
    def __init__(self):
        # Google Cloud Speech クライアントの初期化
        # JSONファイルがある場合はそれを使用、なければADCを使用
        try:
            if CREDENTIALS_PATH.exists():
                credentials = service_account.Credentials.from_service_account_file(
                    str(CREDENTIALS_PATH)
                )
                self.client = speech.SpeechClient(credentials=credentials)
                print("✅ サービスアカウントキーで認証しました")
            else:
                # Application Default Credentials (ADC) を使用
                self.client = speech.SpeechClient()
                print("✅ Application Default Credentials (ADC) で認証しました")
        except Exception as e:
            print(f"⚠️  認証エラー: {e}")
            print("⚠️  'gcloud auth application-default login' を実行してください")
            self.client = None
        
        # ストリーミング設定
        self.config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
            model="latest_long",
            use_enhanced=True,
        )
        
        self.streaming_config = speech.StreamingRecognitionConfig(
            config=self.config,
            interim_results=False,  # 確定した結果のみ取得
        )
        
        # PyAudioの初期化
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.audio_queue = queue.Queue()

        # 入力デバイス選択（任意）
        # - PYAUDIO_LIST_DEVICES=1 で一覧表示
        # - PYAUDIO_INPUT_DEVICE_INDEX=3 のように index 指定
        # - PYAUDIO_INPUT_DEVICE_NAME_CONTAINS="MacBook" のように部分一致指定
        self.input_device_index = None
        self._input_device_info = None

        if os.getenv("PYAUDIO_LIST_DEVICES", "false").lower() in ("1", "true", "yes"):
            try:
                print("\n🎙️  [PyAudio] 入力デバイス一覧:")
                for i in range(self.audio.get_device_count()):
                    info = self.audio.get_device_info_by_index(i)
                    if int(info.get("maxInputChannels", 0)) <= 0:
                        continue
                    name = info.get("name", "?")
                    rate = info.get("defaultSampleRate", "?")
                    ch = info.get("maxInputChannels", "?")
                    print(f"  - index={i}: {name} (channels={ch}, defaultRate={rate})")
                print("")
            except Exception as e:
                print(f"⚠️  [PyAudio] デバイス一覧の取得に失敗: {e}")
        
    def start_audio_stream(self):
        """マイク入力ストリームを開始"""
        if self.stream is None or not self.stream.is_active():
            # デバイス選択
            selected_index = None
            index_env = os.getenv("PYAUDIO_INPUT_DEVICE_INDEX")
            name_contains = os.getenv("PYAUDIO_INPUT_DEVICE_NAME_CONTAINS")

            if index_env:
                try:
                    selected_index = int(index_env)
                except ValueError:
                    print(f"⚠️  [PyAudio] PYAUDIO_INPUT_DEVICE_INDEX が不正です: {index_env}")
                    selected_index = None
            elif name_contains:
                needle = name_contains.lower()
                try:
                    for i in range(self.audio.get_device_count()):
                        info = self.audio.get_device_info_by_index(i)
                        if int(info.get("maxInputChannels", 0)) <= 0:
                            continue
                        if needle in str(info.get("name", "")).lower():
                            selected_index = i
                            break
                except Exception as e:
                    print(f"⚠️  [PyAudio] デバイス検索に失敗: {e}")

            if selected_index is None:
                try:
                    selected_index = int(self.audio.get_default_input_device_info().get("index"))
                except Exception:
                    selected_index = None

            self.input_device_index = selected_index
            try:
                if self.input_device_index is not None:
                    self._input_device_info = self.audio.get_device_info_by_index(self.input_device_index)
                    print(f"🎙️  [PyAudio] 入力デバイス: index={self.input_device_index} name={self._input_device_info.get('name','?')}")
            except Exception as e:
                print(f"⚠️  [PyAudio] 入力デバイス情報の取得に失敗: {e}")

            self.stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                # macOS対応: コールバックを使わない
                stream_callback=None,
                input_device_index=self.input_device_index,
            )
            self.stream.start_stream()
            print("🎤 マイク入力を開始しました")
    
    def stop_audio_stream(self):
        """マイク入力ストリームを停止"""
        if self.stream is not None:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            print("🎤 マイク入力を停止しました")
    
    def audio_generator(self):
        """音声データをストリーミングで生成（ブロッキング読み取り）"""
        level_meter = os.getenv("AUDIO_LEVEL_METER", "false").lower() in ("1", "true", "yes")
        last_print = 0.0
        while True:
            # リスニングが一時停止中はスキップ
            if not listening_event.is_set():
                time.sleep(0.01)
                continue
            
            try:
                # ブロッキングで音声データを読み取り
                chunk = self.stream.read(CHUNK, exception_on_overflow=False)

                if level_meter:
                    now = time.monotonic()
                    if now - last_print >= 1.0:
                        try:
                            rms = audioop.rms(chunk, 2)  # 16-bit = 2 bytes
                            print(f"🔊 [MIC] rms={rms}")
                        except Exception:
                            pass
                        last_print = now

                yield chunk
            except Exception as e:
                print(f"⚠️  音声読み取りエラー: {e}")
                break
    
    def process_responses(self, responses):
        """Google Speech-to-Textからのレスポンスを処理"""
        for response in responses:
            if not response.results:
                continue
            
            result = response.results[0]
            if not result.alternatives:
                continue
            
            transcript = result.alternatives[0].transcript.strip()
            
            if result.is_final and transcript:
                print(f"✅ [STT] 認識完了: {transcript}")
                yield transcript
    
    def cleanup(self):
        """クリーンアップ処理"""
        try:
            self.stop_audio_stream()
        except Exception as e:
            print(f"⚠️  音声ストリーム停止エラー: {e}")
        
        try:
            if self.audio:
                self.audio.terminate()
        except Exception as e:
            print(f"⚠️  PyAudio終了エラー: {e}")


def transcription_worker(loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
    """
    音声認識を実行するワーカースレッド
    """
    print("🚀 Google Cloud Speech-to-Text エンジンを初期化中...")
    
    engine = SpeechToTextEngine()
    
    if engine.client is None:
        print("⚠️  Google Cloud Speech クライアントが初期化されていません")
        print("⚠️  ダミーモードで待機します（音声認識は行われません）")
        stop_event.wait()
        return
    
    print("✅ 初期化完了")
    print("\n🎤 音声を待機中... (話しかけてください。Ctrl+Cで停止)")
    
    try:
        # マイク入力を開始
        engine.start_audio_stream()
        
        while not stop_event.is_set():
            try:
                # リスニングが一時停止中は、Googleのストリーミングセッション自体を開始しない
                # （音声を送らずに待つと Audio Timeout になるため）
                while not listening_event.is_set() and not stop_event.is_set():
                    time.sleep(0.05)

                # 音声ストリームを生成
                audio_generator = engine.audio_generator()
                
                # Google Speech-to-Text APIにリクエスト送信
                requests = (
                    speech.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator
                )
                
                # ストリーミング認識を実行
                responses = engine.client.streaming_recognize(
                    engine.streaming_config, requests
                )
                
                # レスポンスを処理
                for transcript in engine.process_responses(responses):
                    # 認識結果をWebSocketクライアントに送信
                    asyncio.run_coroutine_threadsafe(
                        broadcast_text(transcript),
                        loop,
                    )
                
            except Exception as exc:
                if not stop_event.is_set():
                    print(f"⚠️  [STT] エラーが発生しました: {exc}")
                    print("🔄 [STT] 3秒後に再接続します...")
                    stop_event.wait(timeout=3)
    
    except KeyboardInterrupt:
        print("\n🛑 音声認識を停止中...")
    except Exception as exc:
        print(f"\n❌ [STT] 致命的なエラー: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        # クリーンアップ
        try:
            engine.cleanup()
            print("✅ 音声認識を終了しました")
        except Exception as e:
            print(f"⚠️  クリーンアップエラー: {e}")


async def async_main():
    """メイン処理"""
    loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    # WebSocketサーバーを起動
    server = await websockets.serve(websocket_handler, host="0.0.0.0", port=8001)
    print("🔌 WebSocketサーバーを起動しました: ws://0.0.0.0:8001/listen")

    # 音声認識ワーカースレッドを起動
    worker = threading.Thread(
        target=transcription_worker,
        args=(loop, stop_event),
        daemon=True,
    )
    worker.start()

    try:
        # サーバーを永続的に実行
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        print("\n🛑 サーバーをシャットダウン中...")
        stop_event.set()
        
        try:
            server.close()
            await server.wait_closed()
        except Exception as e:
            print(f"⚠️  サーバークローズエラー: {e}")
        
        # ワーカースレッドの終了を待機
        try:
            await asyncio.to_thread(worker.join, timeout=5)
        except Exception as e:
            print(f"⚠️  ワーカースレッド終了エラー: {e}")
        
        # 接続中のクライアントをクローズ
        for ws in list(connected_clients):
            try:
                await ws.close()
            except Exception:
                pass
        connected_clients.clear()
        
        print("✅ サーバーを終了しました")


if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n🛑 終了します...")
