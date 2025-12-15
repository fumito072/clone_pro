"""LLM server entrypoint.

デフォルトは OpenAI を使用。
Gemini を使う場合は run_llm_server_gemini.py を直接起動してください。
"""

import uvicorn

from run_llm_server_openai import MODEL_NAME, app


if __name__ == "__main__":
    print("=" * 60)
    print("🧠 Narisawa LLM Server (OpenAI) を起動します")
    print("=" * 60)
    print(f"モデル: {MODEL_NAME}")
    print("エンドポイント: http://127.0.0.1:8002/think")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8002)
