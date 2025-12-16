# Unity + Looking Glass + CosyVoice(TTS) 連携メモ

##
UnityはWebSocket/HTTPでTTSサーバーにテキストを投げ、返ってきた音声（WAV/PCM）を再生できます。
再生中の音量(RMS)やViseme推定で口パク（BlendShape）も可能です。
Looking Glassは「Unity側で表示する先」がホログラフィックになるだけで、音声連携は通常のUnityと同じです。

---

## 推奨アーキテクチャ（ローカル開発）
Mac:
- ポートフォワード: `localhost:8004` → VM `127.0.0.1:8002`

Unity:
- `ws://127.0.0.1:8004/tts` に接続してTTS要求
- 返ってきた音声を `AudioSource` で再生
- 再生中にRMSで口の開きを制御（最小実装）

---

## 1) 接続（Mac → VM）
READMEに informs がある通り:

```bash
gcloud compute ssh cosyvoice-tts-server --zone=asia-east1-c --project=hosipro -- -N -L 8004:127.0.0.1:8002
```

---

## 2) Unity側：WebSocketクライアント
### ライブラリ候補
- NativeWebSocket（Unity向け。WebGLにも対応しやすい）
- WebSocketSharp（エディタ/スタンドアロン中心）

このプロジェクトでは「JSONでtext/speaker_id/streamを送る」想定。

### 送信例（概念）
```json
{
  "text": "こんにちは。テストです。",
  "speaker_id": "narisawa2",
  "stream": false
}
```

> 注意: サーバーが返す形式（binary WAVか、base64 JSONか、chunkedか）は実装依存。
> まずは `stream:false` で「1回でWAVが返る」形に寄せるのが簡単。

---

## 3) Unity側：WAVをAudioClipにして再生
### 方針
- 受け取ったWAV bytesをデコードして `AudioClip.Create` に流し込む
- `AudioSource.clip = clip; audioSource.Play();`

WAVデコードは自作でも可能だが、まずは「PCM16/mono/24000Hz」前提で最小実装がおすすめ。

---

## 4) 口パク（最小実装：RMSで口を開く）
### 必要条件
- モデルに `BlendShape`（例: `MouthOpen`）がある
- Unityで `SkinnedMeshRenderer` を取得できる

### 処理
- `AudioSource.GetOutputData()` で波形を取り、RMSを計算
- RMS → 0..100 にマップしてBlendShape weightに入れる

疑似コード:
```csharp
float[] buf = new float[1024];
audioSource.GetOutputData(buf, 0);
float sum = 0f;
for (int i = 0; i < buf.Length; i++) sum += buf[i] * buf[i];
float rms = Mathf.Sqrt(sum / buf.Length);

// 調整用ゲイン
float mouth = Mathf.Clamp01(rms * 20f);
skinnedMesh.SetBlendShapeWeight(mouthOpenIndex, mouth * 100f);
```

---

## 5) Visemeでちゃんとやる（発展）
- 音声→phoneme/viseme推定（外部ライブラリ or 解析）→BlendShapeへ
- まずRMS版で“喋ってる感”を作ってからVisemeに進むのが早い

---

## 6) Looking Glass側
- Looking Glass Unity Pluginを導入
- カメラ/レンダリング設定はプラグイン手順に従う
- 音声・口パクの仕組みは通常のUnityと同じ（表示先がLooking Glassになるだけ）

---

## 7) 運用Tips
- 1回目が遅い対策: サーバー起動後にウォームアップ合成を1回実行
- 同時要求が来るなら: 推論はキュー化（OOMと遅延スパイクを回避）
- ネットワーク越しの遅延が気になるなら: 音声ストリーミング返却にする