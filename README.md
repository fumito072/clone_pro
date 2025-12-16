# President Clone システム

音声認識（STT）、LLM、音声合成（TTS）、顔生成（Face）を統合したクローンシステム

## 🏗️ アーキテクチャ

### システム全体構成（Google Cloud統合）

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Google Cloud Platform                        │
│                                                                       │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐              │
│  │  👂 耳 (STT) │   │  🧠 頭 (LLM) │   │  😀 顔 (Face) │              │
│  │  Cloud      │──>│  Gemini API │──>│  MediaPipe   │              │
│  │  Speech API │   │  + RAG      │   │  Wav2Lip     │              │
│  │  WebSocket  │   │             │   │  Lip Sync    │              │
│  └─────────────┘   └─────────────┘   └──────────────┘              │
│         ↑                 │                   ↑                      │
│         │                 ↓                   │                      │
│  ┌──────┴─────────────────┴───────────────────┴──────────────┐     │
│  │              👄 口 (TTS) - CosyVoice2-0.5B                 │     │
│  │              GCP Compute Engine (Tesla T4 GPU)             │     │
│  │              + LoRA Fine-tuned Model (2-layer)             │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                ↓                                     │
│                                      │
└─────────────────────────────────────────────────────────────────────┘
                                 ↑
                                 │
                      ┌──────────┴──────────┐
                      │  🎮 Controller (Mac) │
                      │  WebSocket 統合制御  │
                      └─────────────────────┘
```

### 詳細フロー図

```
1️⃣ 音声入力 → 音声認識
   [マイク] → [ears_stt (Google Cloud Speech API)] 
              ↓ (WebSocket)
              [テキスト: "こんにちは"]

2️⃣ テキスト → LLM処理
   [テキスト] → [head_llm (Gemini API + RAG)]
              ↓ (ストリーミング)
              [応答テキスト: "こんにちは。今日はいい天気ですね"]

3️⃣ テキスト → 音声合成（GPU加速）
   [応答テキスト] → [mouth_tts (CosyVoice2-0.5B + LoRA)]
                   - GCP VM (Tesla T4 GPU, 15GB VRAM)
                   - 2層LoRAファインチューニング:
                     • Flow層: 音響特徴の調整
                     • LLM層: 韻律・話し方の調整
                   ↓ (WebSocket)
                   [音声データ (24kHz WAV)]

4️⃣ 音声 → リップシンク動画生成
   [音声データ] → [face_wav2lip (MediaPipe)]
                 ↓
                 [リップシンク動画 (音声埋め込み)]

5️⃣ 動画出力
   [動画ファイル] → [ffplay で再生]
                   ↓
                   [ユーザーに出力]
```

### コンポーネント詳細

#### 1. **👂 耳 (STT)**: Google Cloud Speech-to-Text API
   - リアルタイム音声認識（ストリーミング）
   - 日本語対応
   - WebSocketサーバー（Port 8001）
   - **デプロイ**: Google Cloud Run

#### 2. **🧠 頭 (LLM)**: Gemini API + RAG
   - Gemini 1.5 Flash API
   - RAG（Retrieval-Augmented Generation）
   - ナレッジベース: `knowledge/narisawa.json`
   - ストリーミング応答
   - **デプロイ**: Google Cloud Run

#### 3. **👄 口 (TTS)**: CosyVoice2-0.5B + 2層LoRAファインチューニング
   - **ベースモデル**: CosyVoice2-0.5B (FunAudioLLM)
   - **ファインチューニング手法**: 2層LoRA（Low-Rank Adaptation）
     - **Flow層**: 音響特徴の微調整（ピッチ、トーン、音質）
     - **LLM層**: 韻律・話し方の学習（イントネーション、リズム、間の取り方）
   - **学習データ**: 約450セグメント（narisawa2）
   - **出力**: 24kHz WAV形式
   - **インフラ**: 
     - Google Cloud Compute Engine
     - GPU: Tesla T4 (15GB VRAM)
     - マシンタイプ: n1-standard-4 (4 vCPU, 15GB RAM)
     - リージョン: asia-east1-c (台湾)
   - WebSocketサーバー（Port 8002）

#### 4. **😀 顔 (Face)**: MediaPipe + Wav2Lip
   - MediaPipeベースのリップシンク生成
   - 音声波形に同期した口の動き
   - 動画に音声を埋め込み
   - **デプロイ**: Google Cloud Run

#### 5. **🎮 Controller**: 統合制御
   - 全コンポーネントのWebSocket通信制御
   - 非同期処理（asyncio）
   - 動画再生制御（ffplay）
   - **実行環境**: ローカル Mac

## 🚀 起動方法

### クラウドデプロイ版（推奨）

すべてのコンポーネントがGoogle Cloudにデプロイされています：

1. **STT、LLM、Faceサーバー**: Google Cloud Run（自動スケーリング）
2. **TTSサーバー**: GCP Compute Engine（Tesla T4 GPU）

#### コントローラーの起動（ローカルMac）

```bash
# 環境変数を設定（.envまたはexport）
export EARS_STT_SERVER_URL="wss://<cloud-run-stt-url>"
export HEAD_LLM_SERVER_URL="https://<cloud-run-llm-url>/think"  # controller.py はHTTP POST /think を叩く
export MOUTH_TTS_SERVER_URL="ws://<gcp-vm-internal-ip>:8002"
export FACE_SERVER_URL="http://<cloud-run-face-url>"

# コントローラー起動
python3 controller.py
```

### ハイブリッド構成（推奨）: MacでSTT/LLM/controller、GCP VMでTTS(GPU)

この構成は「音声入力と再生はMac」「音声合成だけVMのGPU」を使います。

#### 事前準備（初回のみ）

**Google Speech-to-Text（ADC + quota project）**

```bash
gcloud config set project hosipro
gcloud services enable speech.googleapis.com --project=hosipro
gcloud auth application-default login
gcloud auth application-default set-quota-project hosipro
```

**LLM（OpenAI版の場合）**

```bash
export OPENAI_API_KEY="sk-..."
```

**macOSマイク権限**

- VS Codeのターミナルで動かすなら「システム設定 → プライバシーとセキュリティ → マイク → VS Code」を許可
- Terminal.appで動かすなら「マイク → Terminal」を許可

#### 起動手順（毎回）

**1) VM（GPU）を起動**

```bash
gcloud compute instances start cosyvoice-tts-server --zone=asia-east1-c --project=hosipro
```

**2) VMでTTSサーバー起動（8002）**

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --command \
'source ~/miniconda3/etc/profile.d/conda.sh && conda activate cosyvoice && cd ~/CosyVoice/api_server && \
 (lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9) && \
 : > tts_server.log && nohup env PYTHONUNBUFFERED=1 python tts_server.py </dev/null > tts_server.log 2>&1 & \
 echo $! > tts_server.pid && sleep 1 && lsof -nP -iTCP:8002 -sTCP:LISTEN && tail -n 5 tts_server.log'
```

※ SSH(22番)が不安定なときは `--tunnel-through-iap` を付けてください。

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap --command \
'source ~/miniconda3/etc/profile.d/conda.sh && conda activate cosyvoice && cd ~/CosyVoice/api_server && \
 (lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9) && \
 : > tts_server.log && nohup env PYTHONUNBUFFERED=1 python tts_server.py </dev/null > tts_server.log 2>&1 & \
 echo $! > tts_server.pid && sleep 1 && lsof -nP -iTCP:8002 -sTCP:LISTEN && tail -n 5 tts_server.log'
```

**3) MacでSSHトンネル（ローカル8004 → VM 8002）**

このコマンドは開いたままにしてください（閉じるとトンネルも切れます）。

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro -- -N -L 8004:127.0.0.1:8002
```

IAP経由にする場合:

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap -- -N -L 8004:127.0.0.1:8002
```

**4) Macで耳（STT）起動（8001）**

```bash
cd ears_stt
source venv/bin/activate
python run_stt_server.py
```

入力が入っているか確認したい場合（RMS表示）:

```bash
cd ears_stt
source venv/bin/activate
AUDIO_LEVEL_METER=1 python run_stt_server.py
```

**5) Macで頭（LLM）起動（8002）**

```bash
cd head_llm
source venv/bin/activate
python run_llm_server.py
```

**6) Macでcontroller起動（TTSはトンネル8004へ）**

```bash
cd ..
export EARS_STT_SERVER_URL="ws://127.0.0.1:8001/listen"
export HEAD_LLM_SERVER_URL="http://127.0.0.1:8002/think"
export MOUTH_TTS_SERVER_URL="ws://127.0.0.1:8004/tts"
export SPEAKER_ID="narisawa2"
export ENABLE_FACE_ANIMATION="false"
export SAVE_MOUTH_OUTPUT="true"
python controller.py
```

補足:

- 初回合成はVM側のモデル初期化で20〜40秒かかることがあります（待ってください）。
- Faceは任意です（デフォルト無効）。

### ローカル開発版

#### ターミナル1: 耳（STT）

```bash
cd ears_stt
python3 run_stt_server.py
```

#### ターミナル2: 頭（LLM）

```bash
cd head_llm
python3 run_llm_server.py  # Gemini API使用（このブランチはGeminiに統一）
```

#### ターミナル3: 顔（Face）

```bash
cd face_wav2lip
python3 run_face_server.py
```

※Faceは任意です（`controller.py` はデフォルトで `ENABLE_FACE_ANIMATION=false`）。
有効にしたい場合は `export ENABLE_FACE_ANIMATION=true` を設定してください。

#### ターミナル4: 口（TTS）※GPU必須

**GCP VM (Tesla T4)で実行:**

```bash
# SSH接続（22番が不安定なら --tunnel-through-iap を付ける）
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro

# VM内で実行
source ~/miniconda3/etc/profile.d/conda.sh
conda activate cosyvoice
cd ~/CosyVoice/api_server

# すでに8002で起動していたら止める（二重起動防止）
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9

# ログに出してバックグラウンド起動
: > tts_server.log
nohup env PYTHONUNBUFFERED=1 python tts_server.py </dev/null > tts_server.log 2>&1 &
echo $! > tts_server.pid
tail -n 10 tts_server.log
```

#### ターミナル5: コントローラー

```bash
python3 controller.py
```

## 📚 ナレッジベース（RAG）の準備

1. `OPENAI_API_KEY` を `.env` などで設定する。
2. ナレッジベースのテキストを `head_llm/knowledge/narisawa.json` に追加する。
3. LLMサーバー起動時に自動的にナレッジベースが読み込まれ、RAGが有効化される。
4. 回答内で根拠となる情報源を引用しながら応答を生成する。

## 🎤 使い方

1. すべてのサーバーとコントローラーを起動
2. マイクに向かって話しかける
3. 音声が認識され、テキストに変換される
4. LLMがRAGを用いて応答を生成
5. TTSが応答を音声に変換
6. （任意）Faceサーバーがリップシンク動画を生成

## 🔧 技術スタック

### フロントエンド（Controller）
- Python 3.10+
- asyncio（非同期処理）
- websockets
- pyaudio（音声入出力）
- ffplay/ffprobe（動画再生）

### バックエンド
- **STT**: Google Cloud Speech-to-Text API
- **LLM**: Google Gemini 1.5 Flash API
- **TTS**: 
  - CosyVoice2-0.5B (FunAudioLLM)
  - PyTorch 2.3.1 + CUDA 12.1
  - DeepSpeed（最適化）
  - LoRA（2層ファインチューニング）
- **Face**: MediaPipe, OpenCV

### インフラ
- **Google Cloud Platform**:
  - Cloud Run（STT, LLM, Face）
  - Compute Engine（TTS - Tesla T4 GPU）
  - Artifact Registry（Dockerイメージ）
- **ローカル**: macOS（Controller）

## 📖 詳細ドキュメント

- [セットアップガイド](SETUP.md) - 初期セットアップ手順
- [デプロイガイド](DEPLOY_GUIDE.md) - クラウドデプロイ手順
- [LoRA音声合成ガイド](LORA_VOICE_SYNTHESIS_GUIDE.md) - TTSファインチューニング
- [STTセットアップ](ears_stt/SETUP.md) - 音声認識の詳細設定
- [Faceセットアップ](face_wav2lip/SETUP.md) - リップシンク設定

## 🔒 GitHub共有前のチェック

```bash
# .env が無視されていることを確認
git check-ignore -v head_llm/.env || true

# 大きい生成物/仮想環境が紛れ込んでいないことを確認
git status --porcelain
```

- `head_llm/.env` はコミットせず、`head_llm/.env.example` をコピーして使ってください。

## 🎯 プロジェクト構成

```
narisawa_clone/
├── controller.py              # メイン制御スクリプト
├── ears_stt/                  # STTサーバー
│   ├── run_stt_server.py
│   └── Dockerfile
├── head_llm/                  # LLMサーバー
│   ├── run_llm_server_gemini.py
│   ├── rag_gemini.py
│   ├── knowledge/
│   │   └── narisawa.json     # ナレッジベース
│   └── Dockerfile
├── mouth_tts/                 # TTSサーバー（GCP VM）
│   ├── lora_narisawa2/       # LoRAモデル（2層）
│   │   ├── flow/             # Flow層モデル
│   │   └── llm/              # LLM層モデル
│   └── speakers_config.json
├── face_wav2lip/              # Faceサーバー
│   ├── run_face_server.py
│   └── Dockerfile
└── README.md
```

## 🚨 トラブルシューティング

### TTSサーバーが起動しない
- CUDA Toolkitがインストールされているか確認: `nvcc --version`
- Conda環境がアクティブか確認: `conda activate cosyvoice`
- GPUが認識されているか確認: `nvidia-smi`

### 動画が再生されない
- ffplayがインストールされているか確認: `which ffplay`
- インストール: `brew install ffmpeg` (macOS)

### 音声認識が動作しない
- Google Cloud Speech APIの認証情報が設定されているか確認
- マイクのアクセス許可を確認

### STTが403（quota projectが無い / API無効）

```bash
gcloud config set project hosipro
gcloud services enable speech.googleapis.com --project=hosipro
gcloud auth application-default login
gcloud auth application-default set-quota-project hosipro
```

### マイク入力が入らない（無音になる）

入力デバイス確認（一覧と音量メータ）:

```bash
cd ears_stt
source venv/bin/activate
PYAUDIO_LIST_DEVICES=1 AUDIO_LEVEL_METER=1 python run_stt_server.py
```

デバイスindex指定:

```bash
PYAUDIO_INPUT_DEVICE_INDEX=2 AUDIO_LEVEL_METER=1 python run_stt_server.py
```

### SSHトンネルが張れない（Exit 255）

- VMが起動しているか: `gcloud compute instances describe cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --format='get(status)'`
- 詳細調査: `gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --troubleshoot`

### TTSが返ってこない / Broken pipe

- VM側TTSは合成に時間がかかります。controllerは接続を保ったまま待つ必要があります。
- VM側のログ確認: `tail -n 200 ~/CosyVoice/api_server/tts_server.log`
- 8002が既に使われている場合はプロセスを止めてから起動（上のVM起動コマンド参照）

詳細なセットアップ方法は各ディレクトリの `SETUP.md` を参照してください。

### GPU VMの停止/起動

```bash
# stop
gcloud compute instances stop cosyvoice-tts-server --zone=asia-east1-c --project=hosipro

# start
gcloud compute instances start cosyvoice-tts-server --zone=asia-east1-c --project=hosipro

#local mac
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro -- -N -L 8004:127.0.0.1:8002

gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro
#これでmacとremote vmとの接続が可能に

```



