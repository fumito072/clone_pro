# Google Cloud Speech-to-Text セットアップガイド

このディレクトリには、Google Cloud Speech-to-Text APIを使用した音声認識（STT）サーバーが含まれています。

## 🚀 クイックスタート

### 1. セットアップスクリプトを実行

```bash
cd ears_stt
chmod +x setup.sh
./setup.sh
```

### 2. Google Cloud 認証情報を取得

以下の手順に従ってサービスアカウントキー（JSON）を取得してください。

## 📋 Google Cloud 設定手順（詳細）

### ステップ1: Google Cloudプロジェクトの作成

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. Googleアカウントでログイン
3. 左上のプロジェクト選択ドロップダウンをクリック
4. 「新しいプロジェクト」をクリック
5. プロジェクト名を入力（例: `president-clone`）
6. 「作成」をクリック

### ステップ2: Speech-to-Text APIの有効化

1. 左側のメニュー → **「APIとサービス」** → **「ライブラリ」**
2. 検索バーに `Cloud Speech-to-Text API` と入力
3. **「Cloud Speech-to-Text API」** を選択
4. **「有効にする」** をクリック

### ステップ3: サービスアカウントの作成

1. 左側のメニュー → **「APIとサービス」** → **「認証情報」**
2. **「認証情報を作成」** → **「サービスアカウント」** を選択
3. サービスアカウントの詳細を入力:
   - **サービスアカウント名**: `stt-service-account` (任意の名前)
   - **サービスアカウントID**: 自動生成される
   - **説明**: `Speech-to-Text API用のサービスアカウント` (任意)
4. **「作成して続行」** をクリック

### ステップ4: ロールの割り当て

1. **「このサービスアカウントにプロジェクトへのアクセスを許可する」** セクションで:
   - **「ロールを選択」** → **「Cloud Speech」** → **「Cloud Speech 管理者」** を選択
2. **「続行」** をクリック
3. **「完了」** をクリック

### ステップ5: JSONキーの作成

1. **「認証情報」** ページで、作成したサービスアカウントをクリック
2. **「キー」** タブをクリック
3. **「鍵を追加」** → **「新しい鍵を作成」** をクリック
4. **「JSON」** を選択
5. **「作成」** をクリック
6. JSONファイルが自動的にダウンロードされます

### ステップ6: 認証情報の配置

1. ダウンロードしたJSONファイルの名前を `google_credentials.json` に変更
2. このファイルを `ears_stt/` ディレクトリに配置

```bash
# ダウンロードフォルダから移動する例
mv ~/Downloads/project-name-xxxxx.json /path/to/PresidentClone/ears_stt/google_credentials.json
```

## 🎯 使用方法

### サーバーの起動

```bash
cd ears_stt
python run_stt_server.py
```

起動すると以下のように表示されます:

```
🚀 Google Cloud Speech-to-Text エンジンを初期化中...
✅ 初期化完了
🔌 WebSocketサーバーを起動しました: ws://0.0.0.0:8001/listen
🎤 マイク入力を開始しました
🎤 音声を待機中... (話しかけてください。Ctrl+Cで停止)
```

### コントローラーからの接続

`controller.py` が自動的にこのサーバーに接続します:

```python
EARS_STT_SERVER_URL = "ws://127.0.0.1:8001/listen"
```

## 🔧 トラブルシューティング

### 認証エラーが発生する場合

```
⚠️ Google Cloud認証情報が見つかりません
```

- `google_credentials.json` が `ears_stt/` ディレクトリにあることを確認
- ファイル名が正確に `google_credentials.json` であることを確認

### APIが有効化されていないエラー

```
google.api_core.exceptions.PermissionDenied: 403 Cloud Speech-to-Text API has not been used...
```

- Google Cloud ConsoleでSpeech-to-Text APIが有効化されているか確認
- 数分待ってから再試行（APIの有効化に時間がかかる場合があります）

### マイクが認識されない

```
❌ [Audio] PyAudioの初期化に失敗しました
```

- macOSの場合: **システム環境設定** → **セキュリティとプライバシー** → **マイク** で、ターミナルまたはPythonにマイクのアクセス権限を付与
- マイクが正しく接続されているか確認

### パッケージのインストールエラー

```bash
# PyAudioのインストールに失敗する場合（macOS）
brew install portaudio
pip install pyaudio
```

## 💰 料金について

Google Cloud Speech-to-Text APIは従量課金制です:

- **無料枠**: 月60分まで無料
- **超過分**: 15秒単位で課金

詳細は[公式料金ページ](https://cloud.google.com/speech-to-text/pricing)を参照してください。

## 🔒 セキュリティ

- `google_credentials.json` は機密情報です
- このファイルは `.gitignore` に追加済みなので、Gitにコミットされません
- **絶対に公開リポジトリにアップロードしないでください**

## 📚 参考リンク

- [Google Cloud Speech-to-Text ドキュメント](https://cloud.google.com/speech-to-text/docs)
- [Python クライアントライブラリ](https://cloud.google.com/speech-to-text/docs/libraries#client-libraries-install-python)
- [ストリーミング認識のベストプラクティス](https://cloud.google.com/speech-to-text/docs/streaming-recognize)

## ✅ 動作確認

正常に動作している場合:

1. サーバーを起動すると、マイクが有効になります
2. 話しかけると、音声が認識されます
3. 認識結果がコントローラーに送信されます
4. コントローラーがLLMサーバーに転送します
5. LLMからの応答がTTSで再生されます

---

問題が解決しない場合は、エラーメッセージを確認してください。
