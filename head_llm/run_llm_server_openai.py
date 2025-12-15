"""
OpenAI版 LLMサーバー
コントローラーからPOST /think でテキストを受け取り、応答を返す
"""
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

from rag_openai import OpenAIRAG


def load_env_from_file():
    """Load env vars from the first .env file found."""
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
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ[key] = value
        break


load_env_from_file()

# OpenAI API Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY が環境変数に設定されていません。")

client = OpenAI(api_key=api_key)

# モデル設定
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
print(f"🤖 使用モデル: {MODEL_NAME}")

# RAG初期化
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
rag = None
if KNOWLEDGE_DIR.exists():
    try:
        rag = OpenAIRAG(knowledge_dir=KNOWLEDGE_DIR)
        print(f"✅ RAG有効化: {len(rag.chunks)}件のナレッジ")
    except Exception as e:
        print(f"⚠️  RAG初期化エラー: {e}")

app = FastAPI(title="Narisawa LLM Server (OpenAI)")


class TextInput(BaseModel):
    text: str


def _build_messages(user_text: str):
    """OpenAI APIに渡すメッセージを構築"""
    system_prompt = (
        "あなたはなりさわもくれんという名前の人間です。\n"
        "ユーザーと自然な会話をしてください。\n"
        "回答は簡潔に、100文字以内を目安にしてください。"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # RAG検索
    if rag and rag.chunks:
        results = rag.search(user_text, top_k=3)
        print(f"📚 RAG検索: {len(results)}件ヒット")
        
        if results:
            context = rag.format_context(results)
            context_message = (
                f"以下は参考情報です。質問に関連する内容があれば自然に活用してください：\n\n"
                f"{context}\n\n"
                f"上記の情報を参考にしつつ、自然な会話を心がけてください。"
            )
            messages.append({"role": "system", "content": context_message})
    
    messages.append({"role": "user", "content": user_text})
    return messages


@app.post("/think")
async def think(input_data: TextInput):
    """テキストを受け取り、LLMの応答を返す"""
    print(f"\n🧠 [LLM] ユーザー入力: {input_data.text}")
    
    try:
        messages = _build_messages(input_data.text)
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            stream=False,
        )
        
        response_text = response.choices[0].message.content
        print(f"✅ [LLM] 応答: {response_text}")
        
        return {"response": response_text}
        
    except Exception as e:
        print(f"❌ [LLM] Error: {e}")
        return {"response": f"エラーが発生しました: {e}"}


@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_NAME}


if __name__ == "__main__":
    print("=" * 60)
    print("🧠 Narisawa LLM Server (OpenAI) を起動します")
    print("=" * 60)
    print(f"モデル: {MODEL_NAME}")
    print("エンドポイント: http://127.0.0.1:8002/think")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8002)
