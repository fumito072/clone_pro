import asyncio
import os
import re
import sys
import json
import base64
import tempfile
import subprocess
import time        # 動画再生待機用
import websockets  # 「耳」(STT)・「口」(TTS) 接続用
import httpx       # 「頭」(LLM) 接続用
import pyaudio     # 「口」(TTS) の音声を再生用
import wave
import io
from datetime import datetime
from pathlib import Path

# --- Google Cloud認証設定 ---
# Application Default Credentials (ADC) を使用する場合は、
# 以下のコメントを解除してプロジェクトIDを設定
# os.environ["GOOGLE_CLOUD_PROJECT"] = "hosipro"

# --- サーバーのアドレス（環境変数で上書き可能） ---
EARS_STT_SERVER_URL = os.getenv("EARS_STT_SERVER_URL", "ws://127.0.0.1:8001/listen")
HEAD_LLM_SERVER_URL = os.getenv("HEAD_LLM_SERVER_URL", "http://127.0.0.1:8002/think")
# Linux WSL上のCosyVoice TTSサーバー（Tailscale経由）
MOUTH_TTS_SERVER_URL = os.getenv("MOUTH_TTS_SERVER_URL", "ws://100.64.94.124:8002/tts")
# MediaPipe顔アニメーションサーバー
FACE_SERVER_URL = os.getenv("FACE_SERVER_URL", "http://127.0.0.1:8003/generate")

# --- LoRA音声合成設定 ---
# narisawa LoRAモデルを使用（Linux側で設定済み）
# 参照音声パスは使用しない（LoRAモードではspk2embedding.ptを使用）
SPEAKER_ID = os.getenv("SPEAKER_ID", "narisawa")  # LoRA学習した話者ID
PROMPT_TEXT = os.getenv("PROMPT_TEXT", "")  # プロンプトテキスト（LoRAモードでは不要）

# --- 音声再生の設定 ---
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # CosyVoiceは 24kHz
CHUNK_SIZE = 1024  # 再生バッファサイズ
OUTPUT_DIR = Path(__file__).resolve().parent

# 環境変数で出力ファイル保存を制御（デフォルト: 保存しない）
SAVE_MOUTH_OUTPUT = os.getenv("SAVE_MOUTH_OUTPUT", "false").lower() in ("1", "true", "yes")

# 顔アニメーション設定
# ローカル統合（ears→llm→mouth）では face は「無いもの」として扱うのが安全なのでデフォルト無効
ENABLE_FACE_ANIMATION = os.getenv("ENABLE_FACE_ANIMATION", "false").lower() in ("1", "true", "yes")
FACE_IMAGE_PATH = Path(__file__).parent / "face_wav2lip" / "narisawa_face.jpg"

# グローバルな再生ストリーム
try:
    p = pyaudio.PyAudio()
    audio_stream = p.open(format=AUDIO_FORMAT,
                          channels=CHANNELS,
                          rate=RATE,
                          output=True)
except Exception as e:
    print(f"🛑 [Audio] PyAudioの初期化に失敗しました: {e}")
    print("    マイクやスピーカーが正しく接続されているか確認してください。")
    exit()

processing_lock: asyncio.Lock | None = None
SENTENCE_SPLIT_REGEX = re.compile(r"(.+?[。？！!?]+)")


def save_audio_result(audio_bytes: bytes) -> Path | None:
    if not audio_bytes:
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = OUTPUT_DIR / f"mouth_output_{timestamp}.wav"
    try:
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(AUDIO_FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(audio_bytes)
    except Exception as exc:
        print(f"⚠️ [Mouth] 音声の保存に失敗しました: {exc}")
        return None
    return output_path

def _split_sentences(buffer: str) -> tuple[list[str], str]:
    """
    ストリーミング中に溜めたテキストから文末（。？！!?のいずれか）の文を取り出し、
    残りのバッファを返す。
    """
    sentences: list[str] = []
    remainder_start = 0
    for match in SENTENCE_SPLIT_REGEX.finditer(buffer):
        sentence = match.group(1).strip()
        if sentence:
            sentences.append(sentence)
        remainder_start = match.end()

    remainder = buffer[remainder_start:]
    return sentences, remainder


async def _generate_face_animation(audio_path: Path) -> Path | None:
    """
    音声ファイルから顔アニメーション動画を生成
    
    Args:
        audio_path: 音声ファイルのパス
        
    Returns:
        生成された動画ファイルのパス（失敗時はNone）
    """
    if not ENABLE_FACE_ANIMATION:
        return None
        
    if not FACE_IMAGE_PATH.exists():
        print(f"⚠️ [Face] 顔画像が見つかりません: {FACE_IMAGE_PATH}")
        return None
    
    print(f"\n🎭 [Face] リップシンク動画生成中...", flush=True)
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 音声ファイルを読み込み
            with open(audio_path, "rb") as f:
                audio_data = f.read()
            
            # multipart/form-dataでリクエスト
            files = {
                "audio": ("audio.wav", audio_data, "audio/wav")
            }
            data = {
                "face_image": str(FACE_IMAGE_PATH)
            }
            
            response = await client.post(FACE_SERVER_URL, files=files, data=data)
            
            if response.status_code == 200:
                # 動画ファイルを保存
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                output_path = OUTPUT_DIR / f"face_output_{timestamp}.mp4"
                
                with open(output_path, "wb") as f:
                    f.write(response.content)
                
                print(f"✅ [Face] 動画生成完了: {output_path.name} ({len(response.content)/1024:.1f}KB)")
                return output_path
            else:
                print(f"🛑 [Face] 動画生成エラー (Status: {response.status_code})")
                print(f"     詳細: {response.text[:200]}")
                return None
                
    except httpx.ConnectError:
        print(f"🛑 [Face] Faceサーバーに接続できません ({FACE_SERVER_URL})")
        print(f"💡 確認: Faceサーバーが起動しているか")
        return None
    except httpx.TimeoutException:
        print(f"🛑 [Face] タイムアウト（動画生成に時間がかかりすぎています）")
        return None
    except Exception as e:
        print(f"🛑 [Face] 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        return None


def _play_video(video_path: Path):
    """
    生成された動画を再生
    ffplayまたはmacOSのデフォルトビューアーで開く
    
    Args:
        video_path: 動画ファイルのパス
    """
    try:
        print(f"🎬 [Face] 動画再生中: {video_path.name}")
        
        # ffplayがあれば使用（ブロッキング再生）
        result = subprocess.run(["which", "ffplay"], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            # ffplayで再生（再生完了まで待機）
            subprocess.run(["ffplay", "-autoexit", "-hide_banner", 
                          "-loglevel", "error", str(video_path)])
        else:
            # macOSのデフォルトプレーヤーで再生（非ブロッキング）
            print(f"💡 [Face] ffplayが見つかりません。デフォルトプレーヤーで開きます")
            subprocess.Popen(["open", str(video_path)], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL)
            # ffprobeで動画の長さを取得
            try:
                result = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries", 
                    "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path)
                ], capture_output=True, text=True)
                duration = float(result.stdout.strip()) if result.returncode == 0 else 3.0
            except:
                duration = 3.0  # デフォルト
            
            print(f"⏳ [Face] 動画再生待機: {duration:.1f}秒")
            time.sleep(duration + 1)  # 余裕を持たせる
            
    except Exception as e:
        print(f"⚠️ [Face] 動画再生エラー: {e}")


async def _infer_and_play_tts(full_text: str):
    """
    Linux上のCosyVoice TTSサーバーにWebSocket経由でテキストを送信し、
    音声を受信・再生する
    """
    if not full_text:
        return

    print(f"\n👄 [Mouth] 音声合成中: '{full_text}'", flush=True)

    try:
        # TTSは合成に時間がかかることがあるため、クライアント側pingで接続が切れないようにする
        async with websockets.connect(
            MOUTH_TTS_SERVER_URL,
            ping_interval=None,
            max_size=None,
        ) as ws:
            # 接続確認メッセージを受信（最初のメッセージ）
            connect_msg = await ws.recv()
            connect_response = json.loads(connect_msg)
            if connect_response.get("status") == "connected":
                print(f"✅ [Mouth] TTS接続確認: {connect_response.get('message')}")
            
            # リクエスト送信（LoRA話者IDは環境変数で切り替え）
            request = {
                "text": full_text,
                "mode": "sft",  # LoRA使用時はsftモード
                "speaker": SPEAKER_ID,
                "stream": False  # ストリーミング無効化（無限ループ回避）
            }
            await ws.send(json.dumps(request))
            
            # 最初のレスポンスを受信
            first_msg = await ws.recv()
            first_response = json.loads(first_msg)
            
            audio_chunks: list[bytes] = []
            played_realtime = False
            
            # ストリーミングモード
            if first_response.get("status") == "start" and first_response.get("stream"):
                print(f"🎵 [Mouth] ストリーミング開始 (format: {first_response.get('format')}, rate: {first_response.get('sample_rate')}Hz)")
                
                # バイナリチャンクを連続受信
                while True:
                    msg = await ws.recv()
                    
                    # JSONメッセージ（done/error）をチェック
                    if isinstance(msg, str):
                        response = json.loads(msg)
                        if response.get("status") == "done":
                            print(f"✅ [Mouth] ストリーミング完了 ({len(audio_chunks)} chunks)")
                            break
                        elif response.get("status") == "error":
                            print(f"🛑 [Mouth] TTSエラー: {response.get('message', '不明なエラー')}")
                            return
                    
                    # バイナリチャンク（音声データ）
                    elif isinstance(msg, bytes):
                        audio_chunks.append(msg)
                        # リアルタイム再生
                        try:
                            audio_stream.write(msg)
                            played_realtime = True
                        except Exception as e:
                            print(f"⚠️ [Mouth] チャンク再生エラー: {e}")
            
            # 非ストリーミングモード
            elif first_response.get("status") == "complete":
                print(f"🎵 [Mouth] 一括音声受信 (format: {first_response.get('format')}, rate: {first_response.get('sample_rate')}Hz, size: {first_response.get('size')} bytes)")
                
                # 音声データ受信
                audio_data = await ws.recv()
                if isinstance(audio_data, bytes):
                    audio_chunks.append(audio_data)
                
                # done メッセージ受信
                done_msg = await ws.recv()
                done_response = json.loads(done_msg)
                if done_response.get("status") == "done":
                    print(f"✅ [Mouth] 一括音声完了")
            
            else:
                print(f"🛑 [Mouth] 予期しないレスポンス: {first_response}")
                return
            
            # 全チャンク結合
            audio_bytes = b''.join(audio_chunks)
            print(f"🔊 [Mouth] 総音声データ: {len(audio_bytes)} bytes ({len(audio_bytes)/48000:.2f}s)")

            # 音声を保存（任意）
            if SAVE_MOUTH_OUTPUT:
                saved = save_audio_result(audio_bytes)
                if saved:
                    print(f"💾 [Mouth] 音声保存: {saved.name}")

            # face無し: 音声をローカルで再生して終了
            if not ENABLE_FACE_ANIMATION:
                if played_realtime:
                    return

                # WAVヘッダ付きかもしれないので両対応
                try:
                    if audio_bytes[:4] == b"RIFF" and b"WAVE" in audio_bytes[:16]:
                        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                            frames = wf.readframes(wf.getnframes())
                        audio_stream.write(frames)
                    else:
                        audio_stream.write(audio_bytes)
                except Exception as exc:
                    print(f"⚠️ [Mouth] 音声再生に失敗しました: {exc}")
                return

            # 音声を一時ファイルに保存
            temp_audio_path = OUTPUT_DIR / f"temp_audio_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.wav"
            try:
                with wave.open(str(temp_audio_path), "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(p.get_sample_size(AUDIO_FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(audio_bytes)
                print(f"💾 [Mouth] 一時音声ファイル保存: {temp_audio_path.name}")
            except Exception as exc:
                print(f"⚠️ [Mouth] 一時音声ファイル保存失敗: {exc}")
                return
            
            # 顔アニメーション生成（リップシンク）
            print(f"🎭 [Face] リップシンク動画生成中...")
            video_path = await _generate_face_animation(temp_audio_path)
            
            if video_path and video_path.exists():
                # 動画を再生（音声も含まれる）
                print(f"▶️  [Face] 動画再生開始: {video_path.name}")
                _play_video(video_path)
                print(f"✅ [Face] 動画再生完了")
                
                # 一時ファイルを削除
                try:
                    temp_audio_path.unlink()
                    video_path.unlink()
                    print(f"🧹 [Face] 一時ファイル削除完了")
                except Exception as e:
                    print(f"⚠️ [Face] 一時ファイル削除失敗: {e}")
            else:
                print(f"🛑 [Face] 動画生成に失敗しました")
                # 一時音声ファイルを削除
                try:
                    temp_audio_path.unlink()
                except Exception as e:
                    pass
                        
    except (ConnectionRefusedError, OSError) as e:
        print(f"🛑 [Mouth] TTSサーバーに接続できません: {e}")
        print(f"💡 確認: Linux上でTTSサーバーが起動しているか ({MOUTH_TTS_SERVER_URL})")
    except asyncio.TimeoutError:
        print(f"🛑 [Mouth] 接続タイムアウト")
    except Exception as e:
        print(f"🛑 [Mouth] 予期しないエラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def stream_to_tts(text_stream_generator):
    """
    LLMから送られてくるテキストを一括でTTSに送信する
    チャンクに分けずに完全な文章を一度に処理
    """
    full_text = ""

    # テキストを全て収集
    async for text_chunk in text_stream_generator:
        if not text_chunk:
            continue
        full_text += text_chunk

    # 改行を追加
    print()

    # 一括で送信
    if full_text.strip():
        await _infer_and_play_tts(full_text.strip())

async def handle_llm_response(text: str):
    """
    頭（LLM）サーバーにテキストを送信し、
    一括で回答を受け取り、TTSに流す
    """
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            print(f"🧠 [Head] 思考中...: '{text}'")
            
            # 一括リクエスト
            response = await client.post(HEAD_LLM_SERVER_URL, json={"text": text})
            
            if response.status_code != 200:
                print(f"🛑 [Head] LLMサーバーエラー (Status: {response.status_code})")
                error_body = response.text
                if error_body:
                    print(f"     詳細: {error_body[:200]}")
                return

            # JSON応答を取得
            result = response.json()
            full_response = result.get("response", "")
            
            print(f"🧠 [Head] 回答生成完了: {len(full_response)}文字")
            print(f"💬 [Head] 回答: {full_response}")
            
            # 完全な応答をTTSに送信（ジェネレーターに変換）
            async def text_generator():
                yield full_response
            
            await stream_to_tts(text_generator())

    except httpx.ConnectError:
        print(f"🛑 [Head] LLMサーバーに接続できません")
        print(f"💡 確認: LLMサーバーが起動しているか ({HEAD_LLM_SERVER_URL})")
    except httpx.TimeoutException:
        print(f"🛑 [Head] LLMサーバーのタイムアウト")
    except Exception as e:
        print(f"🛑 [Head] 予期しないエラー: {e}")

async def run_controller():
    """
    メインのコントローラー
    耳（STT）サーバーに接続し、テキストを待機する
    """
    global processing_lock
    if processing_lock is None:
        processing_lock = asyncio.Lock()

    print("=" * 60)
    print("🚀 President Clone コントローラーを起動します")
    print("=" * 60)
    print(f"\n🔌 接続先:")
    print(f"  👂 耳 (STT): {EARS_STT_SERVER_URL}")
    print(f"  🧠 頭 (LLM): {HEAD_LLM_SERVER_URL}")
    print(f"  👄 口 (TTS): {MOUTH_TTS_SERVER_URL}")
    print(f"  🎭 顔 (Face): {FACE_SERVER_URL} {'✅ 有効' if ENABLE_FACE_ANIMATION else '❌ 無効'}")
    if ENABLE_FACE_ANIMATION:
        print(f"     顔画像: {FACE_IMAGE_PATH} {'✅' if FACE_IMAGE_PATH.exists() else '❌ 未設定'}")
    print(f"\n💡 ヒント:")
    print(f"  - Google Cloud Speech-to-Text APIを使用")
    print(f"  - CosyVoice2-0.5Bで音声合成")
    if ENABLE_FACE_ANIMATION:
        print(f"  - Wav2Lipで顔アニメーション生成")
    print(f"  - 話しかけると自動的に認識・応答します")
    print("=" * 60)
    
    print(f"\n👂 [Ears] STTサーバーに接続中...")
    
    retry_count = 0
    max_retries = 3
    
    while retry_count < max_retries:
        try:
            async with websockets.connect(EARS_STT_SERVER_URL) as websocket:
                print("✅ [Ears] 接続成功！音声を待機中...\n")
                
                # リスニング再開を指示
                try:
                    await websocket.send("RESUME_LISTENING")
                except Exception as e:
                    print(f"⚠️  [Ears] リスニング再開コマンド送信失敗: {e}")
                
                async for stt_text in websocket:
                    message = stt_text.strip()
                    
                    # 空のメッセージをスキップ
                    if not message:
                        continue
                    
                    # ステータスメッセージの処理
                    if message.upper().startswith("ACK:"):
                        print(f"📨 [Ears] {message}")
                        continue
                    
                    if message.upper().startswith("STATE:"):
                        state = message.split(":", 1)[1].strip()
                        if state == "LISTENING":
                            print(f"🎤 [Ears] リスニング中...")
                        elif state == "PAUSED":
                            print(f"⏸️  [Ears] リスニング一時停止")
                        continue
                    
                    # 音声認識結果を受信
                    print(f"\n{'=' * 60}")
                    print(f"👂 [Ears] 音声認識結果: '{message}'")
                    print(f"{'=' * 60}")

                    # リスニングを一時停止（応答中は音声認識しない）
                    try:
                        await websocket.send("PAUSE_LISTENING")
                    except Exception as e:
                        print(f"⚠️  [Ears] リスニング停止コマンド送信失敗: {e}")
                    
                    # LLMに送信して応答を取得・再生
                    async with processing_lock:
                        try:
                            await handle_llm_response(message)
                        except Exception as e:
                            print(f"🛑 [処理エラー] {e}")
                        finally:
                            # リスニングを再開
                            try:
                                await websocket.send("RESUME_LISTENING")
                                print(f"\n{'=' * 60}")
                                print(f"🎤 [Ears] 次の音声を待機中...")
                                print(f"{'=' * 60}\n")
                            except Exception as e:
                                print(f"⚠️  [Ears] リスニング再開コマンド送信失敗: {e}")
                
                # 接続が正常に終了した場合はリトライしない
                break

        except websockets.exceptions.ConnectionClosedError as e:
            retry_count += 1
            print(f"🛑 [Ears] サーバーとの接続が切れました: {e}")
            if retry_count < max_retries:
                print(f"🔄 {retry_count}/{max_retries}回目の再接続を試みます（3秒後）...")
                await asyncio.sleep(3)
            else:
                print(f"❌ [Ears] 最大再接続回数に達しました。")
                
        except ConnectionRefusedError:
            print(f"\n🛑 [Ears] STTサーバーに接続できません。")
            print(f"💡 以下を確認してください:")
            print(f"  1. STTサーバーが起動しているか")
            print(f"     → cd ears_stt && python3 run_stt_server.py")
            print(f"  2. ポート8001が使用可能か")
            print(f"  3. Google Cloud認証が完了しているか")
            print(f"     → gcloud auth application-default login")
            break
            
        except Exception as e:
            retry_count += 1
            print(f"🛑 [Ears] 予期しないエラー: {e}")
            if retry_count < max_retries:
                print(f"🔄 {retry_count}/{max_retries}回目の再接続を試みます（3秒後）...")
                await asyncio.sleep(3)
            else:
                print(f"❌ [Ears] 最大再接続回数に達しました。")
                break
    
    # 終了処理
    print("\n🧹 クリーンアップ中...")
    try:
        if audio_stream.is_active():
            audio_stream.stop_stream()
        audio_stream.close()
        p.terminate()
        print("✅ オーディオストリームを終了しました")
    except Exception as e:
        print(f"⚠️  オーディオストリーム終了エラー: {e}")

# --- スクリプトの実行 ---
if __name__ == "__main__":
    try:
        asyncio.run(run_controller())
    except KeyboardInterrupt:
        print("\n🛑 コントローラーを終了します。")
