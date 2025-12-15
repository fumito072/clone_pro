# 🚀 デプロイ前チェックリスト

## ✅ 必須準備

### 1. Google Cloud認証
```bash
# ログイン
gcloud auth login

# デフォルトプロジェクト設定
gcloud config set project president-clone-1762149165

# Application Default Credentials設定
gcloud auth application-default login
```

### 2. 必要なAPIを有効化
```bash
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable speech.googleapis.com
```

### 3. Google Cloud認証情報の準備
STT用の認証情報を配置：
```bash
# ears_stt/google_credentials.json が存在することを確認
ls -la ears_stt/google_credentials.json
```

### 4. OpenAI API Keyの準備
デプロイ時に入力を求められます（事前に用意してください）

### 5. WSL TTS サーバーの起動確認
```bash
# Tailscale経由で接続できるか確認
curl ws://100.64.94.124:8002/health
```

## 🚀 デプロイ実行

### 簡単デプロイ（推奨）
```bash
./deploy.sh
```

### 手動デプロイ
個別にサービスをデプロイする場合：

```bash
# 1. STT Server
cd ears_stt
gcloud run deploy ears-stt \
  --source . \
  --region=asia-northeast1 \
  --allow-unauthenticated

# 2. LLM Server
cd ../head_llm
gcloud run deploy head-llm \
  --source . \
  --region=asia-northeast1 \
  --allow-unauthenticated

# 3. Face Server
cd ../face_wav2lip
gcloud run deploy face-server \
  --source . \
  --region=asia-northeast1 \
  --allow-unauthenticated

# 4. Controller
cd ..
gcloud run deploy controller \
  --source . \
  --region=asia-northeast1 \
  --allow-unauthenticated
```

## 🔧 デプロイ後の設定

### 環境変数の確認
```bash
# Controllerの環境変数を確認
gcloud run services describe controller \
  --region=asia-northeast1 \
  --format=json | jq '.spec.template.spec.containers[0].env'
```

### 環境変数の更新
TTS接続先を変更する場合：
```bash
gcloud run services update controller \
  --set-env-vars MOUTH_TTS_SERVER_URL="ws://新しいIP:8002/tts" \
  --region=asia-northeast1
```

## 🧪 動作テスト

### 1. 各サービスのヘルスチェック
```bash
# STT
curl https://ears-stt-xxxxx-an.a.run.app/health

# LLM
curl https://head-llm-xxxxx-an.a.run.app/health

# Face
curl https://face-server-xxxxx-an.a.run.app/health

# Controller
curl https://controller-xxxxx-an.a.run.app/health
```

### 2. ログ確認
```bash
# リアルタイムログ
gcloud run logs tail controller --region=asia-northeast1

# 過去のログ
gcloud run logs read controller --region=asia-northeast1 --limit=50
```

### 3. エンドツーエンドテスト
Controllerにアクセスして音声入力をテスト

## ⚠️ トラブルシューティング

### WSL接続エラー
```
Error: Connection to ws://100.64.94.124:8002/tts failed
```

**原因**: 
- WSL TTSサーバーが起動していない
- Tailscaleが切断されている
- Cloud RunからTailscaleネットワークにアクセスできない

**解決策**:
1. WSL側でTTSサーバーを起動
2. Tailscaleの接続確認
3. Cloud RunのVPC設定確認（必要に応じて）

### メモリ不足エラー
```
Error: Memory limit exceeded
```

**解決策**:
```bash
# メモリを増やす
gcloud run services update ears-stt \
  --memory=4Gi \
  --region=asia-northeast1
```

### タイムアウトエラー
```
Error: Request timeout
```

**解決策**:
```bash
# タイムアウトを延長
gcloud run services update controller \
  --timeout=3600 \
  --region=asia-northeast1
```

## 💰 コスト管理

### 予算アラート設定
```bash
gcloud billing budgets create \
  --billing-account=YOUR_BILLING_ACCOUNT \
  --display-name="Narisawa Clone Budget" \
  --budget-amount=5000JPY \
  --threshold-rule=percent=80
```

### 使用していない時はmin-instancesを0に
```bash
gcloud run services update controller \
  --min-instances=0 \
  --region=asia-northeast1
```

### リソース削除
```bash
# 全サービス削除
gcloud run services delete ears-stt --region=asia-northeast1 --quiet
gcloud run services delete head-llm --region=asia-northeast1 --quiet
gcloud run services delete face-server --region=asia-northeast1 --quiet
gcloud run services delete controller --region=asia-northeast1 --quiet

# Artifact Registry削除
gcloud artifacts repositories delete narisawa-clone \
  --location=asia-northeast1 --quiet
```

## 📊 監視とログ

### Cloud Consoleでの確認
- Cloud Run: https://console.cloud.google.com/run
- Logs: https://console.cloud.google.com/logs
- Metrics: https://console.cloud.google.com/monitoring

### アラート設定
```bash
# エラー率が高い場合にアラート
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="High Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=0.05
```

## 🔄 更新とロールバック

### コードを更新してデプロイ
```bash
# 変更をプッシュ
git add .
git commit -m "Update controller"
git push

# 再デプロイ
./deploy.sh
```

### ロールバック
```bash
# 以前のリビジョンを確認
gcloud run revisions list --service=controller --region=asia-northeast1

# 特定のリビジョンにロールバック
gcloud run services update-traffic controller \
  --to-revisions=controller-00002-abc=100 \
  --region=asia-northeast1
```

## 🎯 本番運用への移行

### WSL → GCE GPU VM移行
1. Compute Engine GPU VMを作成
2. CosyVoiceをインストール
3. 環境変数を更新：
```bash
gcloud run services update controller \
  --set-env-vars MOUTH_TTS_SERVER_URL="ws://10.128.0.2:8002/tts" \
  --region=asia-northeast1
```

### カスタムドメイン設定
```bash
gcloud run domain-mappings create \
  --service=controller \
  --domain=narisawa.your-domain.com \
  --region=asia-northeast1
```
