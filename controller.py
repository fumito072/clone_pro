import asyncio
import os
import re
import sys
import json
import base64
import websockets  # 「耳」(STT)・「口」(TTS) 接続用
import httpx       # 「頭」(LLM) 接続用
import pyaudio     # 「口」(TTS) の音声を再生用
import wave
from datetime import datetime
from pathlib import Path

# --- Google Cloud認証設定 ---
# Application Default Credentials (ADC) を使用する場合は、
# 以下のコメントを解除してプロジェクトIDを設定
# os.environ["GOOGLE_CLOUD_PROJECT"] = "president-clone-1762149165"

# --- サーバーのアドレス ---
EARS_STT_SERVER_URL = "ws://127.0.0.1:8001/listen"
HEAD_LLM_SERVER_URL = "http://127.0.0.1:8002/think"
# Linux WSL上のCosyVoice TTSサーバー（Tailscale経由）
MOUTH_TTS_SERVER_URL = "ws://100.64.94.124:8002/tts"

# --- Zero-Shot音声クローン設定 ---
# yotaro_segment_0000.wavを使用（Linux側のパス）
PROMPT_AUDIO_PATH = "/mnt/c/Users/fhoshina/development/CosyVoice/my_voice.wav"
# サンプル音声のテキスト（実際に話している内容）
PROMPT_TEXT = "日本でどこでも見ることができるコーヒーチェーンのタリーズってアメリカが発祥なんですけども実は2012年に経営破綻しておりましてその6年後には"

# --- 音声再生の設定 ---
AUDIO_FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000  # CosyVoiceは 24kHz
CHUNK_SIZE = 1024  # 再生バッファサイズ
OUTPUT_DIR = Path(__file__).resolve().parent

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


async def _infer_and_play_tts(full_text: str):
    """
    Linux上のCosyVoice TTSサーバーにWebSocket経由でテキストを送信し、
    音声を受信・再生する
    """
    if not full_text:
        return

    print(f"\n👄 [Mouth] 音声合成中: '{full_text}'", flush=True)

    try:
        async with websockets.connect(MOUTH_TTS_SERVER_URL, timeout=30) as ws:
            # 接続確認メッセージを受信（最初のメッセージ）
            connect_msg = await ws.recv()
            connect_response = json.loads(connect_msg)
            if connect_response.get("status") == "connected":
                print(f"✅ [Mouth] TTS接続確認: {connect_response.get('message')}")
            
            # リクエスト送信
            request = {
                "text": full_text,
                "mode": "zero_shot",
                "prompt_text": PROMPT_TEXT,
                "prompt_audio_path": PROMPT_AUDIO_PATH
            }
            await ws.send(json.dumps(request))
            
            # 音声データレスポンスを受信（2番目のメッセージ）
            response_text = await ws.recv()
            response = json.loads(response_text)
            
            if response.get("status") == "success":
                # Base64エンコードされた音声データをデコード
                audio_base64 = response["audio"]
                audio_bytes = base64.b64decode(audio_base64)
                
                # 音声を再生
                print(f"🔊 [Mouth] 再生中...", end="", flush=True)
                audio_stream.write(audio_bytes)
                
                # 音声を保存
                saved_path = save_audio_result(audio_bytes)
                if saved_path:
                    print(f" ✅ 保存: {saved_path.name}")
            else:
                error_msg = response.get("error", "不明なエラー")
                print(f"🛑 [Mouth] TTSエラー: {error_msg}")
                        
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
    「頭」(LLM)から送られてくるテキストストリームを
    文単位でまとめ、「口」(TTS)に multipart/form-data で送信する
    """
    buffer = ""

    async for text_chunk in text_stream_generator:
        if not text_chunk:
            continue
        print(text_chunk, end="", flush=True)
        buffer += text_chunk

        sentences, buffer = _split_sentences(buffer)
        for sentence in sentences:
            await _infer_and_play_tts(sentence)

    remaining = buffer.strip()
    if remaining:
        await _infer_and_play_tts(remaining)

async def handle_llm_response(text: str):
    """
    頭（LLM）サーバーにテキストを送信し、
    ストリーミングで回答を受け取り、TTSに流す
    """
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            print(f"🧠 [Head] 思考中...: '{text}'")
            
            async with client.stream("POST", HEAD_LLM_SERVER_URL, json={"text": text}) as response:
                
                if response.status_code != 200:
                    print(f"🛑 [Head] LLMサーバーエラー (Status: {response.status_code})")
                    error_body = await response.aread()
                    if error_body:
                        print(f"     詳細: {error_body.decode(errors='ignore')[:200]}")
                    return

                print("🧠 [Head] 回答生成中: ", end="", flush=True)
                
                # LLMからのテキストストリームをTTSに流す
                await stream_to_tts(response.aiter_text())
                
                print()  # 回答の最後に改行

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
    print(f"\n� 接続先:")
    print(f"  👂 耳 (STT): {EARS_STT_SERVER_URL}")
    print(f"  🧠 頭 (LLM): {HEAD_LLM_SERVER_URL}")
    print(f"  👄 口 (TTS): {MOUTH_TTS_SERVER_URL}")
    print(f"\n💡 ヒント:")
    print(f"  - Google Cloud Speech-to-Text APIを使用")
    print(f"  - CosyVoice2-0.5Bで音声合成")
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
