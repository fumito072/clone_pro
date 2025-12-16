# CosyVoice2 LoRA学習 - 成功への道のり

## 概要

CosyVoice2-0.5Bに対してLoRAファインチューニング（LLM層 + Flow層）を行い、声質クローンを成功させた記録。

## 環境

- **VM**: GCP `cosyvoice-tts-server` (asia-east1-c)
- **GPU**: NVIDIA T4 (16GB VRAM)
- **モデル**: CosyVoice2-0.5B
- **データ**: 266サンプル（narisawa2音声）

---

## 🔴 最初に遭遇した問題

### 問題1: 「1 epoch = 1 step」で学習が進まない

**症状:**
- 学習が一瞬で終わる
- epochは進むがbatchが1つしかない
- lossがほとんど出ない

**根本原因:**
```yaml
# ❌ 間違った設定
token_max_length: 0
token_min_length: 0
```

`token_max_length: 0` は「無制限」ではなく、**filterで全サンプルが除外される**という致命的な問題だった。

**解決:**
```yaml
# ✅ 正しい設定
token_max_length: 400
token_min_length: 1
```

### 問題2: lossが表示されない

**原因:** CosyVoiceの`log_per_step()`は`logging.debug()`で出力するため、通常のINFOログには表示されない。

**確認方法:** `train.log`を直接確認すると`DEBUG`レベルでlossが記録されている。

### 問題3: PyTorch互換性エラー

**症状:**
```
AttributeError: 'ProcessGroup' object has no attribute 'options'
```

**原因:** `cosyvoice_join()`が`group_join.options._timeout`を参照しているが、PyTorchバージョンによってはこの属性がない。

**解決:** `cosyvoice/utils/train_utils.py`を修正:
```python
def cosyvoice_join(group_join, info_dict):
    world_size = int(os.environ.get('WORLD_SIZE', 1))
    # ...
    
    # Single GPU: skip join entirely
    if world_size <= 1:
        return False
    
    # timeout を直接指定
    dist.monitored_barrier(group=group_join,
                           timeout=datetime.timedelta(seconds=60))
```

---

## ✅ 成功した設定

### YAML設定（train_lora_llm_flow.yaml）

```yaml
# データパイプライン
train_data_pipeline:
  - conf:
      shuffle_size: 500        # 小さめに
      sort_size: 500           # 小さめに
    processor: shuffle
  - conf:
      max_length: 40960
      min_length: 0
      token_max_length: 400    # ⭐ 重要: 0にしない
      token_min_length: 1      # ⭐ 重要: 0にしない
    processor: filter
  - conf:
      max_frames_in_batch: 400 # ⭐ 低メモリ環境では小さく
    processor: dynamic_batch

# 学習設定
train_conf:
  optim_conf:
    lr: 0.00001               # 1e-5
  scheduler_conf:
    warmup_steps: 200
  max_epoch: 30               # LLM/Flow共通
  accum_grad: 8               # ⭐ 小バッチを補うため大きく
  log_interval: 1
  save_per_step: 100
```

### 重要パラメータの意味

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| `token_max_length` | 400 | これを0にすると全データがフィルタされる |
| `token_min_length` | 1 | 最小トークン長 |
| `max_frames_in_batch` | 400 | T4(16GB)では400程度が安全 |
| `accum_grad` | 8 | 勾配累積で実効バッチサイズを確保 |
| `shuffle_size` | 500 | メモリ節約のため小さめ |

---

## 📊 学習結果

### LLM LoRA
- **Epochs**: 30
- **最終チェックポイント**: `epoch_29_whole.pt`
- **状態**: 正常完了

### Flow LoRA
- **Epochs**: 84
- **最終チェックポイント**: `epoch_83_whole.pt`
- **TRAIN loss**: ~0.03-0.07（収束）
- **CV loss**: ~0.47（安定）
- **状態**: 正常完了（過学習防止のため手動停止）

---

## 🛠 学習コマンド

### LLM学習
```bash
cd ~/CosyVoice
source ~/miniconda3/etc/profile.d/conda.sh
conda activate cosyvoice

torchrun --nnodes=1 --nproc_per_node=1 \
  --rdzv_backend=c10d --rdzv_endpoint=localhost:0 \
  cosyvoice/bin/train.py \
  --train_engine torch_ddp \
  --config lora_narisawa2/train_lora_llm_flow.yaml \
  --train_data lora_narisawa2/parquet/data.list \
  --cv_data lora_narisawa2/parquet/data.list \
  --model llm \
  --checkpoint pretrained_models/CosyVoice2-0.5B/llm.pt \
  --model_dir lora_narisawa2_trained_llm \
  --tensorboard_dir lora_narisawa2_trained_llm/tensorboard \
  --ddp.dist_backend nccl \
  --num_workers 2 \
  --prefetch 100
```

### Flow学習
```bash
torchrun --nnodes=1 --nproc_per_node=1 \
  --rdzv_backend=c10d --rdzv_endpoint=localhost:0 \
  cosyvoice/bin/train.py \
  --train_engine torch_ddp \
  --config lora_narisawa2/train_lora_llm_flow.yaml \
  --train_data lora_narisawa2/parquet/data.list \
  --cv_data lora_narisawa2/parquet/data.list \
  --model flow \
  --checkpoint pretrained_models/CosyVoice2-0.5B/flow.pt \
  --qwen_pretrain_path pretrained_models/CosyVoice2-0.5B/CosyVoice-BlankEN \
  --model_dir lora_narisawa2_trained_flow \
  --tensorboard_dir lora_narisawa2_trained_flow/tensorboard \
  --ddp.dist_backend nccl \
  --num_workers 2 \
  --prefetch 100
```

---

## 🔍 デバッグ方法

### バッチ数の確認
学習が正しく動くか事前に確認するPythonスニペット:

```python
import sys
sys.path.insert(0, '/home/hoshinafumito/CosyVoice')
from cosyvoice.dataset.dataset import Dataset

# config読み込み
import yaml
with open('lora_narisawa2/train_lora_llm_flow.yaml') as f:
    config = yaml.safe_load(f)

# token_max_lengthを確認
for p in config.get('train_data_pipeline', []):
    if p.get('processor') == 'filter':
        print("filter conf:", p.get('conf'))

# Datasetをイテレートしてバッチ数カウント
ds = Dataset(
    data_list_file='lora_narisawa2/parquet/data.list',
    data_pipeline=config['train_data_pipeline'],
    mode='train',
    shuffle=True,
    partition=True
)
count = sum(1 for _ in ds)
print(f"TOTAL batches: {count}")
```

**期待値**: `max_frames_in_batch=400`で約240バッチ程度

---

## 📁 ファイル構成

```
~/CosyVoice/
├── lora_narisawa2/
│   ├── train_lora_llm_flow.yaml    # 学習設定
│   ├── parquet/
│   │   └── data.list               # 学習データリスト
│   ├── spk2embedding.pt            # 話者埋め込み
│   └── segments/                   # 音声セグメント
├── lora_narisawa2_trained_llm/
│   └── epoch_29_whole.pt           # LLM最終チェックポイント
├── lora_narisawa2_trained_flow/
│   └── epoch_83_whole.pt           # Flow最終チェックポイント
└── api_server/
    └── speaker_config.json         # TTSサーバー設定
```

---

## 💡 重要な教訓

1. **`token_max_length: 0`は使わない** - 全データがフィルタされる
2. **低メモリ環境では`max_frames_in_batch`を小さく** - T4では400程度
3. **`accum_grad`で実効バッチサイズを確保** - 8以上推奨
4. **単一GPUでは`cosyvoice_join`のパッチが必要** - world_size=1で早期リターン
5. **学習ログはDEBUGレベル** - `train.log`を直接確認する
6. **Flow学習はmel/token整合が重要** - 公式YAMLの`compute_fbank`設定を維持

---

## 🎯 TTSサーバー設定

学習済みモデルを使用するための`speaker_config.json`:

```json
{
  "speakers": {
    "narisawa2": {
      "type": "lora",
      "llm_lora_model_path": "/home/hoshinafumito/CosyVoice/lora_narisawa2_trained_llm/epoch_29_whole.pt",
      "flow_lora_model_path": "/home/hoshinafumito/CosyVoice/lora_narisawa2_trained_flow/epoch_83_whole.pt",
      "spk_embedding_path": "/home/hoshinafumito/CosyVoice/lora_narisawa2/spk2embedding.pt",
      "description": "narisawa2 (LLM epoch29 + Flow epoch83 LoRA)",
      "active": true
    }
  },
  "default_speaker": "narisawa2"
}
```

---

## 参考

- 元の参考ドキュメント: `FINETUNING.md`
- CosyVoice公式: https://github.com/FunAudioLLM/CosyVoice
