# 🚀 WSL → GCP 完全移行ガイド

## 📊 移行の概要

### Before: WSL + Tailscale
```
Mac (Cloud Run)
  ↓ Tailscale VPN
WSL (自宅PC)
  - 常時起動必要 ❌
  - 不安定なネット接続 ❌
  - 電気代 ❌
```

### After: 完全GCP
```
Google Cloud
├── Cloud Run (STT/LLM/Face/Controller)
└── Compute Engine GPU VM (TTS)
    - 24時間安定稼働 ✅
    - 低レイテンシ ✅
    - スケーラブル ✅
```

---

## 💰 コスト比較

### WSL構成
- Cloud Run: $10-30/月
- 自宅PC電気代: $30-50/月
- **合計: $40-80/月** + 自宅PCの摩耗

### 完全GCP構成
- Cloud Run: $10-30/月
- Compute Engine (N1 + T4 GPU): $0.50/時間
  - 24時間稼働: $360/月
  - **8時間/日稼働: $120/月**
  - **使用時のみ起動: $20-50/月**
- **推奨: 使用時のみ起動 = $30-80/月**

---

## 🔧 移行手順

### ステップ1: GPU VM作成（10分）

```bash
# VM作成
./create_tts_vm.sh

# GPU Quotaリクエストが必要な場合
# https://console.cloud.google.com/iam-admin/quotas?project=hosipro
# 検索: "NVIDIA T4 GPUs" または "GPUs (all regions)"
# リクエスト: 1 GPU（通常即時承認）
```

### ステップ2: VMセットアップ（30分）

```bash
# VMに接続
gcloud compute ssh cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --project=hosipro

# VM内でセットアップ実行
bash setup_cosyvoice_gcp.sh

# 完了したらログアウト
exit
```

### ステップ3: LoRAモデルアップロード（5分）

```bash
# ローカルから実行
./upload_models.sh
```

### ステップ4: TTSサーバーファイルアップロード（3分）

```bash
# WSLからtts_server.pyをコピー
# ローカルに保存されている場合
gcloud compute scp /path/to/tts_server.py \
  cosyvoice-tts-server:~/CosyVoice/api_server/ \
  --zone=asia-northeast1-a
```

### ステップ5: TTSサーバー起動（5分）

```bash
./start_tts_server.sh
```

### ステップ6: 内部IPアドレス取得

```bash
# VM内部IPを取得
INTERNAL_IP=$(gcloud compute instances describe cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --format='get(networkInterfaces[0].networkIP)')

echo "TTS Server IP: ${INTERNAL_IP}"
```

### ステップ7: deploy.sh更新

```bash
# deploy.shのTTS_SERVER_URLを更新
# 変更前: ws://100.64.94.124:8002/tts
# 変更後: ws://<INTERNAL_IP>:8002/tts
```

### ステップ8: 再デプロイ

```bash
# Controllerを更新
gcloud run services update controller \
  --set-env-vars MOUTH_TTS_SERVER_URL="ws://${INTERNAL_IP}:8002/tts" \
  --region=asia-northeast1 \
  --project=hosipro
```

---

## ✅ 動作確認

### TTSサーバーログ確認

```bash
gcloud compute ssh cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --command='sudo journalctl -u cosyvoice-tts -f'
```

### エンドツーエンドテスト

```bash
# Controllerにアクセスして音声入力テスト
curl https://controller-xxxxx-an.a.run.app/health
```

---

## 🔄 運用Tips

### コスト最適化: 使わない時は停止

```bash
# VM停止（ディスク代のみ請求 ~$5/月）
gcloud compute instances stop cosyvoice-tts-server \
  --zone=asia-northeast1-a

# VM起動
gcloud compute instances start cosyvoice-tts-server \
  --zone=asia-northeast1-a

# 起動後、TTSサーバーは自動起動（systemd設定済み）
```

### 自動起動・停止スケジュール

```bash
# Cloud Schedulerで平日9-18時のみ起動
# 朝9時起動
gcloud scheduler jobs create http start-tts-vm \
  --schedule="0 9 * * 1-5" \
  --uri="https://compute.googleapis.com/compute/v1/projects/hosipro/zones/asia-northeast1-a/instances/cosyvoice-tts-server/start" \
  --http-method=POST \
  --oauth-service-account-email=YOUR_SERVICE_ACCOUNT

# 夜18時停止
gcloud scheduler jobs create http stop-tts-vm \
  --schedule="0 18 * * 1-5" \
  --uri="https://compute.googleapis.com/compute/v1/projects/hosipro/zones/asia-northeast1-a/instances/cosyvoice-tts-server/stop" \
  --http-method=POST \
  --oauth-service-account-email=YOUR_SERVICE_ACCOUNT
```

### ログ監視

```bash
# エラーログのみ表示
gcloud compute ssh cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --command='sudo journalctl -u cosyvoice-tts -p err -f'
```

---

## 🆘 トラブルシューティング

### GPU Quotaエラー

```
ERROR: Quota 'NVIDIA_T4_GPUS' exceeded. Limit: 0.0 in region asia-northeast1.
```

**解決策**:
1. https://console.cloud.google.com/iam-admin/quotas?project=hosipro
2. 検索: "NVIDIA T4 GPUs"
3. リージョン: asia-northeast1
4. "EDIT QUOTAS" → 1 GPU リクエスト

### TTSサーバーが起動しない

```bash
# ログ確認
gcloud compute ssh cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --command='sudo journalctl -u cosyvoice-tts -n 100'

# 手動起動テスト
gcloud compute ssh cosyvoice-tts-server \
  --zone=asia-northeast1-a

conda activate cosyvoice
cd ~/CosyVoice/api_server
python tts_server.py
```

### Cloud RunからTTSに接続できない

```bash
# ファイアウォール確認
gcloud compute firewall-rules list --filter="name=allow-cosyvoice-internal"

# VM内部IPが正しいか確認
gcloud compute instances describe cosyvoice-tts-server \
  --zone=asia-northeast1-a \
  --format='get(networkInterfaces[0].networkIP)'

# Controllerの環境変数確認
gcloud run services describe controller \
  --region=asia-northeast1 \
  --format='value(spec.template.spec.containers[0].env)'
```

---

## 📋 チェックリスト

移行前:
- [ ] WSL上のLoRAモデルをバックアップ
- [ ] tts_server.pyファイルを保存
- [ ] GPU Quotaを確認

移行中:
- [ ] GPU VM作成
- [ ] CosyVoiceセットアップ
- [ ] LoRAモデルアップロード
- [ ] TTSサーバー起動確認

移行後:
- [ ] 内部IP取得
- [ ] deploy.sh更新
- [ ] Controller再デプロイ
- [ ] エンドツーエンドテスト
- [ ] WSL停止可能

---

## 🎯 期待される改善

- ✅ **安定性**: WSL再起動不要
- ✅ **レイテンシ**: GCP内部ネットワーク（<10ms）
- ✅ **可用性**: 24時間安定稼働
- ✅ **スケーラビリティ**: 必要に応じてGPU増強
- ✅ **管理性**: Cloud Consoleで一元管理
