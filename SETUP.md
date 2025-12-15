# President Clone - セットアップガイド

音声認識→LLM→音声合成の統合システム

## システム構成

```
Mac (STT + LLM + TTS + Controller)
    ↓ 音声処理パイプライン
```

### コンポーネント

- **Ears (STT)**: Google Cloud Speech-to-Text
- **Head (LLM)**: OpenAI GPT-4o-mini
- **Mouth (TTS)**: CosyVoice2-0.5B (Zero-Shot)
- **Controller**: 統合制御

## 前提条件

### Mac環境
- Python 3.10以上
- Google Cloud SDK
- PyAudio
- マイクとスピーカー

## セットアップ手順

### 1. Mac側のセットアップ

#### Google Cloud認証

```bash
gcloud auth application-default login
```

認証後、quota projectを設定してください：

```bash
# ADCに対してquota projectを明示的に設定（推奨）
gcloud auth application-default set-quota-project YOUR_PROJECT_ID

# または、環境変数で設定（ターミナルセッションごと）
export GCLOUD_QUOTA_PROJECT=YOUR_PROJECT_ID
```

YOUR_PROJECT_IDは、[Google Cloud Console](https://console.cloud.google.com/)で確認できます。

設定後、以下で確認できます：
```bash
gcloud auth application-default print-access-token
```

#### 各モジュールのインストール

**Ears (STT)**
```bash
cd ears_stt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Head (LLM)**
```bash
cd head_llm
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .envファイルを作成
echo "OPENAI_API_KEY=your_api_key_here" > .env
echo "GEMINI_API_KEY=your_api_key_here" >> .env
```

**Controller**
```bash
cd /Users/csc-r196/clone_pro
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 起動方法

## 起動方法

**Terminal 1: STT Server**
```bash
cd ears_stt
source venv/bin/activate
python run_stt_server.py
```

**Terminal 2: LLM Server**
```bash
cd head_llm
source venv/bin/activate
python run_llm_server.py
```

**Terminal 3: TTS Server**
```bash
cd mouth_tts
source venv/bin/activate
python tts_server.py
```

**Terminal 4: Controller**
```bash
cd /Users/csc-r196/clone_pro
python controller.py
```

## 動作確認

マイクに向かって話しかけると：
1. 音声認識（STT）
2. LLMが応答生成
3. 音声合成（TTS）
4. Macのスピーカーから再生

## トラブルシューティング

### マイクが認識されない
```bash
# マイク権限を確認
システム環境設定 → セキュリティとプライバシー → マイク
```

### TTS接続エラー
```bash
# サーバーが起動しているか確認
# Terminal 3で実行されているか確認
```

### Google Cloud認証エラー

**エラー:**
```
Your application is authenticating by using local Application Default Credentials. 
The speech.googleapis.com API requires a quota project, which is not set by default.
```

**原因:** Application Default Credentials (ADC) にquota projectが設定されていない

**対処法:**
```bash
# ADCに対してquota projectを明示的に設定（推奨）
gcloud auth application-default set-quota-project YOUR_PROJECT_ID

# または、環境変数で設定（ターミナルセッションごと）
export GCLOUD_QUOTA_PROJECT=YOUR_PROJECT_ID

# 設定確認
gcloud auth application-default print-access-token
```

その後、STTサーバーを再起動してください。

## カスタマイズ

### システムプロンプトの変更
`head_llm/run_llm_server.py`のシステムメッセージを編集

## ネットワーク構成

```
Mac
├── STT: ws://0.0.0.0:8001/listen
├── LLM: http://0.0.0.0:8002/think
├── TTS: ws://0.0.0.0:8003/tts
└── Controller
```

## ライセンス

各コンポーネントのライセンスに従います：
- CosyVoice: Apache 2.0
- Google Cloud Speech-to-Text: Google Cloud利用規約
- OpenAI API: OpenAI利用規約
