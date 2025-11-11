import asyncio
import os
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import OpenAI  # OpenAIライブラリ
from pydantic import BaseModel

# RAGは後で実装するため、一旦無効化
_rag_disabled = True

# --- 1. 設定 ---

def load_env_from_file():
    """Load env vars from the first .env file found in the usual project locations."""
    candidate_paths = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in candidate_paths:
        if not env_path.is_file():
            continue
        with env_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if not key or key in os.environ:
                    continue
                if len(value) >= 2 and ((value[0] == value[-1]) and value[0] in ("'", '"')):
                    value = value[1:-1]
                os.environ[key] = value
        break

load_env_from_file()

# APIキーを環境変数から読み込む
# （.env または export OPENAI_API_KEY="sk-..." で設定しておく）
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY が環境変数に設定されていません。")

client = OpenAI(api_key=api_key)

# 社長クローンのペルソナ（人格）を設定
SYSTEM_PROMPT = "あなたは日本を代表する企業の社長です。威厳を持ち、洞察力に富み、しかし簡潔に回答してください。語尾は「～だ。」「～かね。」「～だろう。」などを使い、断定的に話してください。"
MODEL = "gpt-4o-mini" # 最新モデル (または gpt-3.5-turbo)
RAG_INSTRUCTION = (
    "以下は社内ナレッジベースから抽出した参考情報だ。"
    "回答では内容を事実ベースで活用し、根拠としたスニペットの番号を文末に[1][2]の形式で並べること。"
    "根拠が不十分な場合はその旨を率直に述べ、追加で確認すべきアクションを提案すること。"
)
MAX_CONTEXT_CHARS = 420

app = FastAPI()

# --- 2. APIが受け取るデータモデルを定義 ---
class TextInput(BaseModel):
    text: str


def _build_messages(user_text: str):
    """
    OpenAIのChatCompletions APIに渡すメッセージを構築
    """
    system_prompt = (
        "あなたは成澤（なりさわ）という名前のキャラクターです。\n"
        "ユーザーと自然な会話をしてください。"
    )
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]


# --- 3. OpenAIからのレスポンスをストリーミングするジェネレータ ---
async def stream_openai_response(messages: List[dict]):
    """OpenAI APIからストリームでレスポンスを取得するジェネレータ"""
    try:
        # OpenAI APIにストリーミングモードでリクエスト
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=True, # ストリーミングを有効化
        )
        
        # 受け取った断片を逐次送信（yield）する
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True) # サーバー側でも確認用に出力
                yield content
                
    except Exception as e:
        print(f"\nOpenAI API Error: {e}")
        yield f"エラーが発生しました: {e}"

# --- 4. FastAPIエンドポイントの定義 ---
@app.post("/think")
async def think(input_data: TextInput):
    """
    STT（耳）からテキストを受け取り、LLM（頭）の回答を
    ストリーミングでコントローラーに返す
    """
    print(f"\n[LLM Request]: {input_data.text}")
    print("[LLM Response]: ", end="")
    messages = _build_messages(input_data.text)

    return StreamingResponse(
        stream_openai_response(messages),
        media_type="text/plain" # テキストを平文としてストリーミング
    )

# --- 5. サーバー起動 ---
if __name__ == "__main__":
    print("Starting FastAPI server for LLM (Head)...")
    # STT (8001) とは別のポート 8002 で起動
    uvicorn.run(app, host="0.0.0.0", port=8002)
