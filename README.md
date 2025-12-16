# President Clone システム

音声認識（STT）、LLM、音声合成（TTS）、顔生成（Face）を統合したクローンシステム

## 使い方（推奨: MacでSTT/LLM/controller、GPU VMでTTS）

### 0) 前提（初回のみ）

**Google Speech-to-Text（ADC + quota project）**

```bash
gcloud config set project hosipro
gcloud services enable speech.googleapis.com --project=hosipro
gcloud auth application-default login
gcloud auth application-default set-quota-project hosipro
```

### 1) GPU VM（TTS）を起動

```bash
gcloud compute instances start cosyvoice-tts-server --zone=asia-east1-c --project=hosipro
```

### 2) GPU VMでTTSサーバー起動（8002）

**初回セットアップ（必要な場合のみ）：**

他ユーザーのディレクトリから環境をコピーした場合は、以下の手順で環境を構築：

```bash
# 1. 他ユーザーのディレクトリをコピー
# ※ YOUR_USER は自分のユーザー名に置き換え
# ※ このコマンドは実行まで時間がかかる
sudo cp -r /home/hoshinafumito /home/YOUR_USER/
sudo chown -R YOUR_USER:YOUR_USER /home/YOUR_USER/hoshinafumito

# 2. Miniconda3 を新規インストール
rm -rf ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p ~/miniconda3
~/miniconda3/bin/conda init bash
source ~/.bashrc

# 3. Conda 利用規約に同意
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 4. cosyvoice 環境を作成（Python 3.11）
conda create -n cosyvoice python=3.11 -y
conda activate cosyvoice

# 5. requirements.txt を更新してインストール
cd ~/hoshinafumito/CosyVoice
sed 's/onnxruntime-gpu==1.18.0/onnxruntime-gpu==1.23.2/g' requirements.txt > requirements_updated.txt
sed -i 's/onnxruntime==1.18.0/onnxruntime==1.23.2/g' requirements_updated.txt
pip install -r requirements_updated.txt

# 6. Git submodule を初期化
git submodule update --init --recursive

# 7. speaker_config.json のパスを修正
# ※ YOUR_USER は自分のユーザー名に置き換え
cd api_server
sed -i 's|/home/hoshinafumito/|/home/YOUR_USER/hoshinafumito/|g' speaker_config.json

# 8. 環境変数を .bashrc に追加
# ※ YOUR_USER は自分のユーザー名に置き換え
echo 'export COSYVOICE_REPO_DIR="/home/YOUR_USER/hoshinafumito/CosyVoice"' >> ~/.bashrc
echo 'export PYTHONPATH="${PYTHONPATH}:${COSYVOICE_REPO_DIR}:${COSYVOICE_REPO_DIR}/third_party/Matcha-TTS"' >> ~/.bashrc
source ~/.bashrc
```

**通常起動手順：**

- ディレクトリ: `~/hoshinafumito/CosyVoice/api_server`
- ポート: `8002`
- まずSSHで入る（IAP推奨）:

```bash
- VM内で起動する（手動手順）:

```bash
# ※ YOUR_USER は自分のユーザー名に置き換え
conda activate cosyvoice
export COSYVOICE_REPO_DIR="/home/YOUR_USER/hoshinafumito/CosyVoice"
export PYTHONPATH="${PYTHONPATH}:${COSYVOICE_REPO_DIR}:${COSYVOICE_REPO_DIR}/third_party/Matcha-TTS"
cd ~/hoshinafumito/CosyVoice/api_server
export COSYVOICE_REPO_DIR="/home/csc-r196/hoshinafumito/CosyVoice"
export PYTHONPATH="${PYTHONPATH}:${COSYVOICE_REPO_DIR}:${COSYVOICE_REPO_DIR}/third_party/Matcha-TTS"
cd ~/hoshinafumito/CosyVoice/api_server

# まず8002が空いてるか確認
lsof -nP -iTCP:8002 -sTCP:LISTEN

# 空いてなければ、掴んでるプロセスを止める（全部）
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill

# それでも残る時だけ強制kill
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9

# サーバー起動
python tts_server.py
```

- 停止（PIDがある場合）:

```bash
# ポートから止める
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill
```

### 3) MacでSSHトンネル（ローカル8004 → VM 8002）

※このコマンドは開いたまま
```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap -- -N -L 8004:127.0.0.1:8002
```

### 4) Macで耳（STT）起動（8001）

```bash
cd ears_stt
source venv/bin/activate
python run_stt_server.py
```

### 5) Macで頭（LLM）起動（8002）

```bash
cd head_llm
source venv/bin/activate
python run_llm_server.py
```

### 6) MacでController起動

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



## GPU VM操作（start/stop/ssh）

```bash
# start
gcloud compute instances start cosyvoice-tts-server --zone=asia-east1-c --project=hosipro

# stop
gcloud compute instances stop cosyvoice-tts-server --zone=asia-east1-c --project=hosipro

# ssh（IAP経由）
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap

# sshが不安定な時の調査
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --troubleshoot --tunnel-through-iap
```

## よくあるトラブル（最小）

### 8002 already in use

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap --command \
'lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9'
```

### STTが403（quota projectが無い / API無効）

```bash
gcloud config set project hosipro
gcloud services enable speech.googleapis.com --project=hosipro
gcloud auth application-default login
gcloud auth application-default set-quota-project hosipro
```
