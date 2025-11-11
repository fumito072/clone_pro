# President Clone システム

音声認識（STT）、LLM、音声合成（TTS）を統合したクローンシステム

## 🏗️ アーキテクチャ

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  👂 耳 (STT) │ ───> │  🧠 頭 (LLM) │ ───> │  👄 口 (TTS) │
│  Google     │      │             │      │  CosyVoice  │
│  Cloud      │      │             │      │  2-0.5B     │
│  Speech API │      │             │      │             │
└─────────────┘      └─────────────┘      └─────────────┘
       ↑                                          │
       │                                          │
       └────────────── controller.py ─────────────┘
```

### コンポーネント

1. **👂 耳 (STT)**: Google Cloud Speech-to-Text API
   - リアルタイム音声認識
   - 日本語対応
   - WebSocket接続

2. **🧠 頭 (LLM)**: LLMサーバー
   - テキスト生成
   - ストリーミング応答

3. **👄 口 (TTS)**: CosyVoice2-0.5B
   - ゼロショット音声合成
   - 24kHz出力
   - プロンプト音声ベース

## 🚀 起動方法

### ターミナル1: 耳（STT）

```bash
cd ears_stt
python3 run_stt_server.py
```

### ターミナル2: 頭（LLM）

```bash
cd head_llm
python3 run_llm_server.py
```

#### RAG（Yotaro Brain）の準備

1. `OPENAI_API_KEY` を `.env` などで設定する。
2. ナレッジベースのテキストを `head_llm/knowledge/yotaro/` 配下に追加する（`.md` または `.txt`）。
3. 埋め込みを生成してインデックスを更新:
   ```bash
   cd head_llm
   python3 build_brain.py --persona yotaro
   ```
4. サーバーを起動すると、生成したインデックスを読み込み、回答内で根拠スニペットを `[1][2]` の形式で引用する。

### ターミナル3: コントローラー

```bash
python3 controller.py
```

## 💬 使い方

1. すべてのサーバーとコントローラーを起動
2. マイクに向かって話しかける
3. 音声が認識され、LLMが応答
4. 応答が音声で再生される

詳細なセットアップ方法は `ears_stt/SETUP.md` を参照してください。
