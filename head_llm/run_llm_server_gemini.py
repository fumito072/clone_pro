import asyncio
import os
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai

# RAG import (Gemini Embeddings版)
try:
    from rag_gemini import GeminiRAG
    RAG_ENABLED = True
except ImportError:
    RAG_ENABLED = False
    print("⚠️  RAG機能は無効です（rag_gemini.pyが見つかりません）")

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

# Google Cloud認証（ADCまたはAPI Key）
# 方法1: API Key使用（簡単）
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    print("✅ Gemini API Key認証")
else:
    # 方法2: Google Cloud ADC使用（推奨）
    print("✅ Google Cloud ADC認証を使用")

# Geminiモデル設定
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")  # デフォルト: Gemini 2.0 Flash
print(f"🤖 使用モデル: {MODEL_NAME}")

# RAG初期化（ナレッジベースがある場合）
rag = None
if RAG_ENABLED:
    knowledge_dir = Path(__file__).parent / "knowledge"
    if knowledge_dir.exists():
        try:
            rag = GeminiRAG(knowledge_dir)
            print(f"✅ RAG有効化: {len(rag.chunks)}件のナレッジ")
        except Exception as e:
            print(f"⚠️  RAG初期化エラー: {e}")
    else:
        print(f"⚠️  ナレッジディレクトリが見つかりません: {knowledge_dir}")

# システムプロンプト
SYSTEM_PROMPT = """あなたは成澤孝人のAIクローンです。
成澤孝人の話し方、性格、知識を忠実に再現してください。

- 丁寧だが親しみやすい口調
- ビジネス・技術に詳しい
- 簡潔で分かりやすい回答
- 必要に応じて具体例を挙げる

ユーザーの質問に対して、成澤孝人として自然に会話してください。
"""

# FastAPIアプリ
app = FastAPI(title="Narisawa LLM Server (Gemini)")

# --- 2. リクエスト・レスポンス定義 ---
class ThinkRequest(BaseModel):
    text: str
    max_tokens: int = 500
    temperature: float = 0.7

# --- 3. LLM推論 ---
async def generate_complete_response(user_text: str, max_tokens: int, temperature: float):
    """
    Gemini APIで一括応答を生成（RAG対応）
    ストリーミングではなく、完全な応答を一度に返す
    """
    try:
        # RAG検索（有効な場合）
        context = ""
        if rag:
            search_results = rag.search(user_text, top_k=3)
            if search_results:
                context = rag.format_context(search_results, max_length=1000)
                print(f"📚 RAG検索: {len(search_results)}件ヒット")
        
        # プロンプト構築
        if context:
            full_prompt = f"""以下の参考情報を踏まえて、ユーザーの質問に答えてください。

【参考情報】
{context}

【ユーザーの質問】
{user_text}
"""
        else:
            full_prompt = user_text
        
        # Geminiモデル初期化
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        )
        
        # 一括生成（stream=False）
        response = model.generate_content(full_prompt, stream=False)
        
        # 完全な応答を返す
        full_text = response.text
        print(f"✅ [LLM] 応答生成完了: {len(full_text)}文字")
        return full_text
    
    except Exception as e:
        error_message = f"Error: {str(e)}"
        print(f"❌ [LLM] {error_message}")
        return error_message

# --- 4. エンドポイント ---

@app.get("/")
async def root():
    return {
        "service": "Narisawa LLM Server",
        "model": MODEL_NAME,
        "api": "Google Gemini",
        "status": "running"
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "model": MODEL_NAME}

@app.post("/think")
async def think(request: ThinkRequest):
    """
    LLM推論エンドポイント（一括応答）
    """
    print(f"\n🧠 [LLM] ユーザー入力: {request.text}")
    
    # 完全な応答を生成
    response_text = await generate_complete_response(
        request.text,
        request.max_tokens,
        request.temperature
    )
    
    return {"response": response_text}

# --- 5. サーバー起動 ---
if __name__ == "__main__":
    print("=" * 60)
    print("🧠 Narisawa LLM Server (Gemini) を起動します")
    print("=" * 60)
    print(f"モデル: {MODEL_NAME}")
    print(f"エンドポイント: http://127.0.0.1:8002/think")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8002)
