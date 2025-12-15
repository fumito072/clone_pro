import asyncio
import os
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from openai import OpenAI  # OpenAIライブラリ
from pydantic import BaseModel

# RAG import (OpenAI Embeddings版)
from rag_openai import OpenAIRAG

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

# RAGを初期化 (OpenAI Embeddings版)
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
print(f"📂 ナレッジディレクトリ: {KNOWLEDGE_DIR}")
rag = OpenAIRAG(knowledge_dir=KNOWLEDGE_DIR) if KNOWLEDGE_DIR.exists() else None

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
    RAGで関連する知識を検索してコンテキストに追加（意味ベース検索）
    """
    # システムプロンプトを構築
    system_prompt = (
        "あなたはなりさわもくれんという名前の人間です。\n"
        "ユーザーと自然な会話をしてください。\n"
        "回答は簡潔に、100文字以内を目安にしてください。"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # RAG検索を実行（OpenAI Embeddings で意味ベース検索）
    if rag and rag.chunks:
        results = rag.search(user_text, top_k=3)
        
        print(f"\n💡 [RAG検索] クエリ: {user_text}")
        print(f"📊 [RAG結果] {len(results)}件の関連情報を検索:")
        for i, result in enumerate(results, 1):
            chunk_id = result.get('id', '?')
            score = result.get('_score', 0.0)  # OpenAIRAGは '_score' キーを使用
            text_preview = result.get('text', '')[:50]
            print(f"   [{i}] {chunk_id} (類似度: {score:.3f}) {text_preview}...")
        
        # RAG結果があればコンテキストを追加
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

# --- 3. OpenAIからのレスポンスを一括取得 ---
async def get_openai_response(messages: List[dict]):
    """OpenAI APIから一括でレスポンスを取得"""
    try:
        # OpenAI APIに一括リクエスト（stream=False）
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            stream=False,  # ストリーミング無効化
        )
        
        # 完全な応答を取得
        full_response = response.choices[0].message.content
        print(f"\n✅ [LLM] 応答生成完了: {len(full_response)}文字")
        print(f"💬 [LLM] 応答: {full_response}")
        
        return full_response
                
    except Exception as e:
        print(f"\n❌ OpenAI API Error: {e}")
        return f"エラーが発生しました: {e}"

# --- 4. FastAPIエンドポイントの定義 ---
@app.post("/think")
async def think(input_data: TextInput):
    """
    STT（耳）からテキストを受け取り、LLM（頭）の回答を
    一括でコントローラーに返す
    """
    print(f"\n[LLM Request]: {input_data.text}")
    print("[LLM Response]: ", end="")
    messages = _build_messages(input_data.text)

    # 一括でレスポンスを取得
    response_text = await get_openai_response(messages)
    
    # JSON形式で完全な応答を返す
    return {"response": response_text}

# --- 5. サーバー起動 ---
if __name__ == "__main__":
    print("Starting FastAPI server for LLM (Head)...")
    # STT (8001) とは別のポート 8002 で起動
    uvicorn.run(app, host="0.0.0.0", port=8002)
