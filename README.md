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

- ディレクトリ: `~/CosyVoice/api_server`
- ポート: `8002`
- まずSSHで入る（IAP推奨）:

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro --tunnel-through-iap
```

- VM内で起動する（手動手順）:

```bash
conda activate cosyvoice
cd ~/CosyVoice/api_server

# まず8002が空いてるか確認
lsof -nP -iTCP:8002 -sTCP:LISTEN

# 空いてなければ、掴んでるプロセスを止める（全部）
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill

# それでも残る時だけ強制kill
lsof -tiTCP:8002 -sTCP:LISTEN | xargs -r kill -9

- 停止（PIDがある場合）:

```bash
cd ~/CosyVoice/api_server
python tts_server.py

# まだ残ってたらポートから止める
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
