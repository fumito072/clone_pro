# President Clone 統合チェックリスト

## ✅ セットアップ確認

### 1. Google Cloud認証
- [ ] `gcloud auth login` 完了
- [ ] `gcloud auth application-default login` 完了
- [ ] プロジェクトID設定: `president-clone-1762149165`
- [ ] Speech-to-Text API 有効化済み

### 2. 環境構築
- [ ] Python 3.10以上インストール済み
- [ ] PyAudioインストール済み
- [ ] websocketsインストール済み
- [ ] httpxインストール済み

### 3. 各コンポーネントの確認

#### 👂 耳 (STT)
- [ ] `ears_stt/run_stt_server.py` 存在確認
- [ ] `ears_stt/requirement.txt` のパッケージインストール済み
- [ ] マイクの権限設定済み（macOSの場合）

#### 🧠 頭 (LLM)  
- [ ] `head_llm/run_llm_server.py` 存在確認
- [ ] LLMサーバーが正常に起動する

#### 👄 口 (TTS)
- [ ] CosyVoiceサーバーURL確認
- [ ] `mouth_tts/CosyVoice/asset/reference_voice_24k.wav` 存在確認
- [ ] スピーカーが正しく接続されている

#### 🎮 コントローラー
- [ ] `controller.py` 存在確認
- [ ] サーバーURLが正しく設定されている

## 🚀 起動テスト

### 手順
1. [ ] ターミナル1でSTTサーバー起動
   ```bash
   cd ears_stt
   python3 run_stt_server.py
   ```
   
2. [ ] ターミナル2でLLMサーバー起動
   ```bash
   cd head_llm
   python3 run_llm_server.py
   ```

3. [ ] ターミナル3でコントローラー起動
   ```bash
   python3 controller.py
   ```

### 期待される出力

#### STTサーバー
```
ℹ️  Application Default Credentials (ADC) を使用します
🔌 WebSocketサーバーを起動しました: ws://0.0.0.0:8001/listen
🚀 Google Cloud Speech-to-Text エンジンを初期化中...
✅ Application Default Credentials (ADC) で認証しました
✅ 初期化完了
🎤 音声を待機中...
```

#### コントローラー
```
============================================================
🚀 President Clone コントローラーを起動します
============================================================

📡 接続先:
  👂 耳 (STT): ws://127.0.0.1:8001/listen
  🧠 頭 (LLM): http://127.0.0.1:8002/think
  👄 口 (TTS): https://4xwmw9vy8oh4vj-8003.proxy.runpod.net/inference_zero_shot

✅ [Ears] 接続成功！音声を待機中...
```

## 🧪 動作テスト

### テスト1: 基本動作
- [ ] マイクに「こんにちは」と話しかける
- [ ] STTサーバーで音声認識される
- [ ] コントローラーに認識結果が表示される
- [ ] LLMサーバーで応答が生成される
- [ ] TTSサーバーで音声合成される
- [ ] スピーカーから応答が再生される

### テスト2: 連続会話
- [ ] 1回目の応答後、再度話しかける
- [ ] 2回目も正常に認識・応答される
- [ ] リスニングの一時停止・再開が正常に動作

### テスト3: エラーハンドリング
- [ ] LLMサーバーを停止した状態でテスト → エラーメッセージ表示
- [ ] TTSサーバーを停止した状態でテスト → エラーメッセージ表示
- [ ] 各サーバー再起動後、正常に復帰

## 🐛 トラブルシューティング

### STTサーバーが起動しない
- [ ] Google Cloud認証を再実行
  ```bash
  gcloud auth application-default login
  ```
- [ ] Speech-to-Text APIが有効か確認
  ```bash
  gcloud services list --enabled | grep speech
  ```

### 音声認識されない
- [ ] マイクの権限を確認（システム環境設定 → セキュリティとプライバシー → マイク）
- [ ] マイクが正しく接続されているか確認
- [ ] STTサーバーのログを確認

### コントローラーが接続できない
- [ ] 各サーバーが起動しているか確認
- [ ] ポート番号が正しいか確認（8001: STT, 8002: LLM, 8003: TTS）
- [ ] ファイアウォール設定を確認

### 音声が再生されない
- [ ] スピーカーが正しく接続されているか確認
- [ ] 音量設定を確認
- [ ] PyAudioが正しくインストールされているか確認

## 📊 パフォーマンスチェック

### レイテンシ
- [ ] 音声認識: < 2秒
- [ ] LLM応答生成開始: < 1秒
- [ ] TTS音声合成: < 3秒
- [ ] 総応答時間: < 5秒

### 音質
- [ ] STT認識精度: 90%以上
- [ ] TTS音声品質: クリアに聞こえる
- [ ] ノイズ・途切れなし

## 🎯 次のステップ

統合が成功したら:
- [ ] プロンプトテキストをカスタマイズ
- [ ] 音声速度を調整
- [ ] LLMモデルの設定を最適化
- [ ] 参照音声を変更して声質をカスタマイズ

---

すべてのチェック項目が完了したら、システムは正常に統合されています！🎉
