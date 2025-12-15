# 🚀 Google Cloudデプロイガイド

## 📊 デプロイ構成

### 現在の構成
```
Mac: STT + LLM + Face + Controller
  ↓ Tailscale (100.64.94.124)
WSL: CosyVoice TTS (GPU)
```

### GCPデプロイ構成（ハイブリッド）
```
┌───────── Google Cloud Run ─────────┐
│ • STT Server (ears_stt)             │
│ • LLM Server (head_llm)             │
│ • Face Server (face_wav2lip)        │
│ • Controller (統合制御)              │
└────────────────────────────────────┘
         ↓ 環境変数で切り替え
    ┌─────────────────┐
    │ WSL (Tailscale) │  ← 開発環境
    │ または             │
    │ GCE (内部IP)     │  ← 本番環境
    │ CosyVoice TTS    │
    └─────────────────┘
```

## 🔧 TTS接続の3つのモード

### モード1: Tailscale継続（開発用）
```bash
# 環境変数設定
export MOUTH_TTS_SERVER_URL="ws://100.64.94.124:8002/tts"
```
- **メリット**: WSLをそのまま使える、初期コスト低
- **デメリット**: WSLマシン常時稼働必要

### モード2: GCE GPU VM（本番用）
```bash
# GCE内部IP
export MOUTH_TTS_SERVER_URL="ws://10.128.0.2:8002/tts"
```
- **メリット**: 完全クラウド化、低レイテンシ
- **コスト**: ~$200/月（N1 + T4 GPU）

### モード3: 外部公開WSL（オプション）
```bash
# Tailscale Funnel/ngrok経由
export MOUTH_TTS_SERVER_URL="wss://your-tts.tailscale.net/tts"
```

## 📦 デプロイ手順

### ステップ1: Secret Managerに認証情報を保存
```bash
# OpenAI API Key
echo -n "sk-..." | gcloud secrets create openai-api-key --data-file=-

# Google Cloud認証（STT用）
gcloud secrets create google-credentials \
  --data-file=ears_stt/google_credentials.json
```

### ステップ2: 各サービスをCloud Runにデプロイ
```bash
# 自動デプロイスクリプト実行
./deploy.sh
```

### ステップ3: TTS接続設定
```bash
# 開発環境（Tailscale WSL）
gcloud run services update controller \
  --set-env-vars MOUTH_TTS_SERVER_URL="ws://100.64.94.124:8002/tts"

# または本番環境（GCE）
gcloud run services update controller \
  --set-env-vars MOUTH_TTS_SERVER_URL="ws://10.128.0.2:8002/tts"
```

## 💰 コスト試算

### パターンA: Cloud Run + WSL (Tailscale)
- Cloud Run: $10-30/月
- WSL: 既存マシン（追加コストなし）
- **合計: ~$20/月**

### パターンB: 完全GCP移行
- Cloud Run: $10-30/月
- Compute Engine (N1 + T4): $150-300/月
- **合計: ~$200/月**

## 🔐 セキュリティ

### Tailscale使用時の注意点
1. **ACL設定**: TTSポート(8002)のみ許可
2. **認証**: Tailscaleのデバイス認証必須
3. **モニタリング**: 接続ログ確認

### GCE使用時
1. **VPC内部通信**: 外部公開不要
2. **IAM**: サービスアカウント利用
3. **Firewall**: 内部IPのみ許可

## 🚀 段階的移行プラン

### フェーズ1: Cloud Run + Tailscale WSL（1週間）
- [ ] Cloud Runデプロイ
- [ ] Tailscale接続確認
- [ ] 動作テスト

### フェーズ2: GCE準備（任意）
- [ ] GCE GPU VM作成
- [ ] CosyVoiceインストール
- [ ] LoRAモデル転送

### フェーズ3: 完全移行（任意）
- [ ] 環境変数切り替え
- [ ] パフォーマンス比較
- [ ] コスト評価

## 📝 環境変数一覧

```bash
# 必須
OPENAI_API_KEY=sk-...
GOOGLE_CLOUD_PROJECT=president-clone-1762149165

# TTS接続（環境に応じて選択）
MOUTH_TTS_SERVER_URL=ws://100.64.94.124:8002/tts  # Tailscale
# MOUTH_TTS_SERVER_URL=ws://10.128.0.2:8002/tts   # GCE内部IP

# オプション
ENABLE_FACE_ANIMATION=true
SPEAKER_ID=narisawa
```

## 🔍 トラブルシューティング

### Tailscale接続が不安定
```bash
# Cloud RunからTailscaleネットワークへの接続確認
gcloud run services update controller \
  --vpc-egress=all-traffic
```

### レイテンシが高い
- WSL → GCE移行を検討
- リージョンを近くに（asia-northeast1）

### コストが高い
- GCE: プリエンプティブルVM使用で50%削減
- Cloud Run: min-instances=0 でアイドル時無料
