import os
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import uvicorn
from TTS.api import TTS # Coqui TTSライブラリ
import io

from torch.serialization import add_safe_globals
try:
    # XTTS v2 が内部の checkpoint で参照しているクラス達を allowlist 登録
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.config.shared_configs import BaseDatasetConfig

    add_safe_globals([
        XttsConfig,
        XttsAudioConfig,
        XttsArgs,
        BaseDatasetConfig,
    ])
    print("[XTTS] Registered safe globals for torch.load (XttsConfig, XttsAudioConfig, XttsArgs, BaseDatasetConfig).")
except Exception as e:
    print(f"[XTTS] Failed to register safe globals (non-fatal): {e}")

# --- 1. 設定 ---
PORT = 8003
SPEAKER_WAV_PATH = "reference_voice.wav"
LANGUAGE = "ja"

# Coqui XTTSv2 の利用規約に事前同意
os.environ.setdefault("COQUI_TOS_AGREED", "1")

app = FastAPI()

# --- 2. モデルのグローバル読み込み ---
print("Loading XTTSv2 model...")

# デバイスの自動検出
device = "cpu"
if torch.backends.mps.is_available():
    device = "mps"
elif torch.cuda.is_available():
    device = "cuda"

print(f"Using device: {device}")



# XTTSv2モデルをロード
# (transformers をアップグレードしたので、今度は正常にロードされるはず)
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=True).to(device)

print("Model loading complete.")

# --- 3. APIが受け取るデータモデル ---
class TextInput(BaseModel):
    text: str

# --- 4. 【重要】本物のオーディオストリーミング ---
def stream_tts_audio(text: str):
    """
    XTTSv2でテキストからオーディオチャンクを
    リアルタイムで生成するジェネレータ
    """
    try:
        print(f"\n[TTS] Generating stream for: '{text[:20]}...'")
        
        # これが「本物」のストリーミング関数です
        # テキストを渡すと、音声チャンクを随時返してくれます
        chunks = tts.tts_stream(
            text=text,
            speaker_wav=SPEAKER_WAV_PATH,
            language=LANGUAGE
        )
        
        print("[TTS] Stream started...")
        # チャンクをクライアントに逐次送信 (yield)
        for i, chunk in enumerate(chunks):
            yield chunk
            
        print("[TTS] Stream finished.")

    except Exception as e:
        print(f"\n[TTS] Error: {e}")
        yield b"" # エラー時も空のストリームを返す

# --- 5. FastAPIエンドポイントの定義 ---
@app.post("/speak")
async def speak(input_data: TextInput):
    """
    「頭（LLM）」からテキストを受け取り、
    オーディオストリームをコントローラーに返す
    """
    # stream_tts_audio ジェネレータをそのまま返す
    return StreamingResponse(
        stream_tts_audio(input_data.text), 
        media_type="audio/wav" # オーディオストリームとして返す
    )

# --- 6. サーバー起動 ---
if __name__ == "__main__":
    print(f"Starting FastAPI server for TTS (Mouth) on port {PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=PORT)