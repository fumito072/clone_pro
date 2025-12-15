# President Clone - セットアップガイド

音声認識→LLM→音声合成の統合システム

## システム構成

```
Mac (STT + LLM + Controller)
    ↓ WebSocket
Windows/WSL2 (TTS Server with GPU)
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

### Windows/WSL2環境
- NVIDIA GPU (RTX 3070以上推奨)
- CUDA 12.1+
- Miniconda3

## セットアップ手順

### 1. Mac側のセットアップ

#### Google Cloud認証
```bash
gcloud auth application-default login
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
```

**Controller**
```bash
cd /Users/hoshinafumito/development/PresidentClone
pip install -r requirements.txt
```

### 2. WSL2側のセットアップ

#### CosyVoiceのインストール
```bash
# WSL2にログイン
cd /mnt/c/Users/YOUR_USERNAME/development

# リポジトリクローン
git clone https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice

# Conda環境作成
conda create -n cosyvoice python=3.10
conda activate cosyvoice

# 依存関係インストール
pip install -r requirements.txt
```

#### モデルのダウンロード
```bash
# ModelScopeからダウンロード
pip install modelscope

python << EOF
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')
EOF

# YAMLファイルの修正
ln -s pretrained_models/CosyVoice2-0.5B/cosyvoice2.yaml pretrained_models/CosyVoice2-0.5B/cosyvoice.yaml
sed -i "s/qwen_pretrain_path: '.*'/qwen_pretrain_path: ''/" pretrained_models/CosyVoice2-0.5B/cosyvoice2.yaml
```

#### TTSサーバーファイルの配置
```bash
# api_serverディレクトリを作成
mkdir -p /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/api_server

# このリポジトリの `api_server/` をWSL側へコピー
# 例）Windows側でこのリポジトリを置いている場合:
#   cp /mnt/c/Users/YOUR_USERNAME/development/narisawa_clone/api_server/cosyvoice_engine.py /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/api_server/
#   cp /mnt/c/Users/YOUR_USERNAME/development/narisawa_clone/api_server/tts_server.py      /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/api_server/
#   cp /mnt/c/Users/YOUR_USERNAME/development/narisawa_clone/api_server/speaker_config.json.example \
#      /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/api_server/speaker_config.json
#
# `speaker_config.json` のパスは、学習済みLoRA（LLM/Flow）と spk2embedding.pt を指定してください。
```

#### Windows Port Forwarding設定
```powershell
# PowerShellを管理者権限で実行
netsh interface portproxy add v4tov4 listenport=8002 listenaddress=0.0.0.0 connectport=8002 connectaddress=YOUR_WSL_IP

# ファイアウォールルール追加
New-NetFirewallRule -DisplayName "WSL TTS Server" -Direction Inbound -LocalPort 8002 -Protocol TCP -Action Allow
```

WSL IPアドレスの確認:
```bash
# WSL内で実行
ip addr show eth0 | grep inet
```

### 3. 音声サンプルの準備

話者の音声サンプル（3〜30秒）を用意し、WSLに配置：
```bash
# 音声ファイルをWSLにコピー
# Windows: C:\Users\YOUR_USERNAME\your_voice.wav
# WSL: /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/my_voice.wav
```

`controller.py` はLoRA話者IDで合成します。
```bash
export SPEAKER_ID="narisawa2"
```

## 起動方法

### 1. WSL側でTTSサーバーを起動
```bash
cd /mnt/c/Users/YOUR_USERNAME/development/CosyVoice/api_server
conda activate cosyvoice
python tts_server.py
```

### 2. Mac側で各サーバーを起動

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

**Terminal 3: Controller**
```bash
cd /Users/hoshinafumito/development/narisawa_clone
# face無し（デフォルト）。必要なら true で有効化。
export ENABLE_FACE_ANIMATION=false
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
# Mac→WSLの接続確認
nc -zv YOUR_TAILSCALE_IP 8002

# Port Forwardingの確認 (Windows PowerShell)
netsh interface portproxy show all
```

### Google Cloud認証エラー
```bash
# 認証を再実行
gcloud auth application-default login
```

## カスタマイズ

### 別の話者に変更
`controller.py`の以下を変更：
```python
PROMPT_AUDIO_PATH = "/path/to/new_speaker.wav"
PROMPT_TEXT = "新しい話者の音声転写"
```

### システムプロンプトの変更
`head_llm/run_llm_server.py`の`_build_messages()`関数内のシステムメッセージを編集

## ネットワーク構成

```
Mac (127.0.0.1)
├── STT: ws://0.0.0.0:8001/listen
├── LLM: http://0.0.0.0:8002/think
└── Controller
    ↓ Tailscale (100.64.94.124)
Windows Host
    ↓ Port Forward (0.0.0.0:8002 → WSL_IP:8002)
WSL2 (172.19.35.59)
└── TTS: ws://0.0.0.0:8002/tts
```

## ライセンス

各コンポーネントのライセンスに従います：
- CosyVoice: Apache 2.0
- Google Cloud Speech-to-Text: Google Cloud利用規約
- OpenAI API: OpenAI利用規約
