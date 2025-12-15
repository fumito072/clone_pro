# LoRA音声合成を動作させるまでの完全手順

## 📋 目次
1. [問題の本質](#問題の本質)
2. [解決までの流れ](#解決までの流れ)
3. [実装の詳細](#実装の詳細)
4. [システム構成](#システム構成)
5. [トラブルシューティング](#トラブルシューティング)

---

## 問題の本質

### CosyVoice2-0.5Bの制約
```python
# CosyVoice2-0.5Bをロード
model = CosyVoice2('/path/to/CosyVoice2-0.5B')

# 問題: 標準のspeaker IDが存在しない
print(model.frontend.spk2info)  # → {} (空の辞書)

# inference_sftは内部でspk2info[spk_id]を参照
# どんなspk_idを渡してもKeyErrorが発生
model.inference_sft("テキスト", "yotaro")  # ❌ KeyError: 'yotaro'
```

**つまり**: LoRAでファインチューニングしても、そのままでは学習した話者IDが使えない。

---

## 解決までの流れ

### ステップ1: LoRAファインチューニングで生成されたファイルの確認

```bash
lora_yotaro/
├── spk2embedding.pt      # ⭐ 話者埋め込み（重要！）
├── spk2utt               # speaker_id: "yotaro"
├── segments/             # 学習用音声ファイル
├── text                  # テキストデータ
└── ...

lora_yotaro_trained/
└── epoch_12_whole.pt     # ⭐ LoRA学習済み重み
```

**重要な発見**:
- `spk2embedding.pt`: 学習時に抽出された話者埋め込みベクトル
- `epoch_12_whole.pt`: LoRA適用後のLLM重み

### ステップ2: 話者埋め込みの構造を確認

```python
import torch

spk2embedding = torch.load('lora_yotaro/spk2embedding.pt')
print(spk2embedding.keys())  # → dict_keys(['yotaro'])
print(type(spk2embedding['yotaro']))  # → <class 'list'>
print(len(spk2embedding['yotaro']))   # → 192
```

**問題点**:
- データ型が `list`（Tensorではない）
- 1次元データ `[192]`（バッチ次元がない）

### ステップ3: 正しい形式に変換

```python
# リスト → Tensor
embedding = torch.tensor(spk2embedding['yotaro'])
print(embedding.shape)  # → torch.Size([192])

# 2次元化（バッチ次元を追加）
embedding = embedding.unsqueeze(0)
print(embedding.shape)  # → torch.Size([1, 192])
```

**なぜ2次元化が必要？**

CosyVoiceの内部コード（`cosyvoice/flow/flow.py`）:
```python
def inference(self, token, embedding, ...):
    # ...
    embedding = F.normalize(embedding, dim=1)  # dim=1 で正規化
    # ...
```

- `F.normalize(..., dim=1)` は「2次元目を正規化」することを意味
- 1次元 `[192]` だと `IndexError: Dimension out of range (expected to be in range of [-1, 0], but got 1)`

### ステップ4: モデルに話者情報を登録

```python
from cosyvoice.cli.cosyvoice import CosyVoice2
import torch

# 1. ベースモデルをロード
model = CosyVoice2('/path/to/CosyVoice2-0.5B')

# 2. LoRA重みをロード
checkpoint = torch.load('lora_yotaro_trained/epoch_12_whole.pt', map_location='cpu')
lora_state_dict = {
    k: v for k, v in checkpoint.items() 
    if k not in ['epoch', 'step', 'optimizer', 'scheduler']
}
model.model.llm.load_state_dict(lora_state_dict, strict=False)

# 3. 話者埋め込みをロード & 変換
spk2embedding = torch.load('lora_yotaro/spk2embedding.pt')
yotaro_emb = torch.tensor(spk2embedding['yotaro']).unsqueeze(0)  # [1, 192]

# 4. ⭐ モデルに話者IDを登録
model.frontend.spk2info['yotaro'] = {
    'embedding': yotaro_emb
}

# 5. ✅ これで動作する！
result = model.inference_sft('こんにちは、よーたろーです', 'yotaro', stream=False)
```

---

## 実装の詳細

### `CosyVoiceEngine` クラス（WSL側）

**ファイル**: `/mnt/c/Users/fhoshina/development/CosyVoice/api_server/cosyvoice_engine.py`

```python
class CosyVoiceEngine:
    def __init__(self, model_dir, speaker_config_path):
        self.model = CosyVoice2(model_dir)
        self._lora_cache = {}        # LoRA重みのキャッシュ
        self._embedding_cache = {}   # 埋め込みのキャッシュ
        self._load_speaker_config()  # speaker_config.json読み込み
    
    def load_speaker_lora(self, speaker_id: str) -> bool:
        """LoRAモデルと話者埋め込みをロード"""
        
        # キャッシュ確認（2回目以降は高速）
        if speaker_id in self._lora_cache:
            self.model.model.llm.load_state_dict(self._lora_cache[speaker_id], strict=False)
            return True
        
        speaker_info = self.speaker_config['speakers'][speaker_id]
        lora_path = speaker_info['lora_model_path']
        embedding_path = speaker_info['spk_embedding_path']
        
        # 1. LoRA重みロード
        checkpoint = torch.load(lora_path, map_location='cpu')
        lora_state_dict = {
            k: v for k, v in checkpoint.items() 
            if k not in ['epoch', 'step', 'optimizer', 'scheduler']
        }
        self.model.model.llm.load_state_dict(lora_state_dict, strict=False)
        
        # 2. 話者埋め込みロード
        spk2embedding = torch.load(embedding_path, map_location='cpu')
        
        # 3. ⭐ 次元変換（重要！）
        if isinstance(spk2embedding[speaker_id], list):
            embedding = torch.tensor(spk2embedding[speaker_id]).unsqueeze(0)
        else:
            embedding = spk2embedding[speaker_id]
            if embedding.dim() == 1:
                embedding = embedding.unsqueeze(0)  # [192] → [1, 192]
        
        # 4. ⭐ モデルに登録
        self.model.frontend.spk2info[speaker_id] = {'embedding': embedding}
        
        # 5. キャッシュ保存
        self._lora_cache[speaker_id] = lora_state_dict
        self._embedding_cache[speaker_id] = embedding
        
        return True
    
    def synthesize_sft(self, text: str, speaker: str, speed: float = 1.0):
        """非ストリーミング音声合成"""
        self.load_speaker_lora(speaker)
        result = list(self.model.inference_sft(text, speaker, stream=False, speed=speed))
        audio = torch.cat([chunk['tts_speech'] for chunk in result], dim=1)
        return audio
    
    def stream_sft_pcm(self, text: str, speaker: str, speed: float = 1.0):
        """ストリーミング音声合成（PCM形式）"""
        self.load_speaker_lora(speaker)
        for chunk in self.model.inference_sft(text, speaker, stream=True, speed=speed):
            if 'tts_speech' in chunk:
                audio_np = chunk['tts_speech'].squeeze(0).cpu().numpy()
                audio_int16 = (audio_np * 32767).astype('int16')
                yield audio_int16.tobytes()
```

### `speaker_config.json` 設定ファイル

**ファイル**: `/mnt/c/Users/fhoshina/development/CosyVoice/api_server/speaker_config.json`

```json
{
  "speakers": {
    "yotaro": {
      "type": "lora",
      "lora_model_path": "/mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro_trained/epoch_12_whole.pt",
      "spk_embedding_path": "/mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro/spk2embedding.pt",
      "description": "Yotaro voice (Epoch 12, Acc 93.0%)",
      "active": true
    }
  },
  "default_speaker": "yotaro"
}
```

### `tts_server.py` WebSocketサーバー（WSL側）

**ファイル**: `/mnt/c/Users/fhoshina/development/CosyVoice/api_server/tts_server.py`

```python
import asyncio
import json
import websockets
from cosyvoice_engine import CosyVoiceEngine

tts_engine: CosyVoiceEngine | None = None

async def websocket_handler(ws):
    await ws.send(json.dumps({
        "status": "connected",
        "message": "TTS Server Ready (Multi-Speaker LoRA Support)"
    }))
    
    async for message in ws:
        req = json.loads(message)
        text = req.get("text")
        speaker = req.get("speaker", "yotaro")
        stream = req.get("stream", False)
        
        if stream:
            # ストリーミング
            await ws.send(json.dumps({
                "status": "start",
                "stream": True,
                "format": "pcm_s16le",
                "channels": 1,
                "sample_rate": 24000
            }))
            
            for pcm_chunk in tts_engine.stream_sft_pcm(text, speaker):
                await ws.send(pcm_chunk)  # バイナリPCM送信
            
            await ws.send(json.dumps({"status": "done"}))

async def main():
    global tts_engine
    tts_engine = CosyVoiceEngine()
    
    async with websockets.serve(websocket_handler, "0.0.0.0", 8002):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
```

### `controller.py` クライアント（Mac側）

**ファイル**: `~/development/PresidentClone/controller.py`

```python
async def _infer_and_play_tts(full_text: str):
    """TTSサーバーに接続して音声を再生"""
    async with websockets.connect(MOUTH_TTS_SERVER_URL) as ws:
        # 接続確認
        connect_msg = await ws.recv()
        
        # リクエスト送信
        request = {
            "text": full_text,
            "mode": "sft",           # ⭐ LoRA使用時はsftモード
            "speaker": "yotaro",     # ⭐ LoRA学習した話者ID
            "stream": True
        }
        await ws.send(json.dumps(request))
        
        # ストリーミング受信 & 再生
        audio_chunks = []
        while True:
            message = await ws.recv()
            
            # JSONメッセージ
            if isinstance(message, str):
                response = json.loads(message)
                if response.get("status") == "done":
                    break
            
            # バイナリPCMデータ
            elif isinstance(message, bytes):
                # ⭐ リアルタイム再生
                audio_stream.write(message)
                audio_chunks.append(message)
        
        # 保存用
        if audio_chunks:
            all_audio = b''.join(audio_chunks)
            save_audio_result(all_audio)
```

---

## システム構成

```
┌─────────────────────────────────────────────────┐
│               Mac側 (Client)                     │
│  ┌───────────────────────────────────────────┐  │
│  │         controller.py                      │  │
│  │  - WebSocket Client                        │  │
│  │  - PyAudio 音声再生                        │  │
│  │  - speaker="yotaro" 指定                   │  │
│  └─────────────────┬─────────────────────────┘  │
└────────────────────┼─────────────────────────────┘
                     │ WebSocket (ws://100.64.94.124:8002)
                     │ {"text": "...", "mode": "sft", "speaker": "yotaro"}
                     ↓
┌─────────────────────────────────────────────────┐
│          WSL/Linux側 (Server)                    │
│  ┌───────────────────────────────────────────┐  │
│  │         tts_server.py                      │  │
│  │  - WebSocket Server (port 8002)           │  │
│  │  - リクエスト受信 → CosyVoiceEngine呼出   │  │
│  └─────────────────┬─────────────────────────┘  │
│                    ↓                             │
│  ┌───────────────────────────────────────────┐  │
│  │      cosyvoice_engine.py                  │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │ load_speaker_lora("yotaro")         │  │  │
│  │  │  1. LoRA重みロード (epoch_12.pt)    │  │  │
│  │  │  2. 埋め込みロード (spk2embedding.pt)│  │  │
│  │  │  3. Tensor変換 [192]→[1,192]        │  │  │
│  │  │  4. spk2info['yotaro']に登録        │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │ synthesize_sft(text, "yotaro")      │  │  │
│  │  │   → model.inference_sft()            │  │  │
│  │  │   → PCMストリーム生成                │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ファイル構成:                                   │
│  /mnt/c/Users/.../CosyVoice/                    │
│  ├── api_server/                                │
│  │   ├── cosyvoice_engine.py                   │
│  │   ├── tts_server.py                         │
│  │   └── speaker_config.json                   │
│  ├── lora_yotaro/                               │
│  │   └── spk2embedding.pt  ← 話者埋め込み      │
│  └── lora_yotaro_trained/                       │
│      └── epoch_12_whole.pt  ← LoRA重み         │
└─────────────────────────────────────────────────┘
```

---

## トラブルシューティング

### 1. `KeyError: 'yotaro'` が発生する

**原因**: `spk2info` に話者IDが登録されていない

**解決策**:
```python
# 確認
print(model.frontend.spk2info.keys())  # 'yotaro' が含まれているか？

# 登録されていない場合
embedding = torch.tensor(spk2embedding['yotaro']).unsqueeze(0)
model.frontend.spk2info['yotaro'] = {'embedding': embedding}
```

### 2. `IndexError: Dimension out of range`

**原因**: 埋め込みが1次元 `[192]` のまま

**解決策**:
```python
# NG: 1次元
embedding = torch.tensor(spk2embedding['yotaro'])  # [192]

# OK: 2次元
embedding = torch.tensor(spk2embedding['yotaro']).unsqueeze(0)  # [1, 192]
```

### 3. 音声が再生されない

**原因**: WebSocketのメッセージ形式が不一致

**確認ポイント**:
- サーバー側: バイナリPCMを直接送信 `await ws.send(pcm_bytes)`
- クライアント側: `isinstance(message, bytes)` で判定して受信

### 4. `ModuleNotFoundError: No module named 'cosyvoice'`

**原因**: PYTHONPATHが設定されていない

**解決策**:
```bash
export PYTHONPATH="/mnt/c/Users/fhoshina/development/CosyVoice:${PYTHONPATH}"
python tts_server.py
```

### 5. メモリ不足（OOM Killer）

**原因**: WSLのメモリ制限

**解決策**: `.wslconfig` で16GB以上に設定
```ini
[wsl2]
memory=16GB
```

---

## キーポイントまとめ

| 項目 | 重要ポイント |
|------|------------|
| **LoRA重み** | `epoch_12_whole.pt` をロード → `model.model.llm.load_state_dict()` |
| **話者埋め込み** | `spk2embedding.pt` から取得 → **必ず2次元** `[1, 192]` に変換 |
| **モデル登録** | `model.frontend.spk2info[speaker_id] = {'embedding': emb}` |
| **推論** | `model.inference_sft(text, speaker_id)` で音声合成 |
| **キャッシュ** | 2回目以降は `_lora_cache` から高速ロード |
| **通信形式** | WebSocketでバイナリPCMをストリーミング送信 |

---

## 参考情報

- **CosyVoice2 GitHub**: https://github.com/FunAudioLLM/CosyVoice
- **学習データ**: 298サンプル（推奨: 500-1000サンプル）
- **学習エポック**: Epoch 12, Accuracy 93.0%
- **音声形式**: PCM s16le, 24kHz, モノラル
- **RTF (Real-Time Factor)**: ~1.0 (リアルタイム生成)

---

## まとめ

**成功の鍵**は以下の3点:

1. ✅ **LoRA重みの正しいロード**: メタデータを除外してLLMに適用
2. ✅ **話者埋め込みの次元変換**: `[192]` → `[1, 192]` (バッチ次元追加)
3. ✅ **spk2infoへの登録**: モデルが話者IDを認識できるようにする

これにより、`controller.py` から `speaker="yotaro"` を指定するだけで、LoRAで学習した声で音声合成ができるようになりました！

---

**作成日**: 2025-11-17  
**プロジェクト**: PresidentClone  
**実装者**: GitHub Copilot + User
