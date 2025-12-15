# CosyVoice LoRA ファインチューニング完全ガイド 🎓

このガイドは、CosyVoice2-0.5BモデルでLoRAファインチューニングを行うための完全なドキュメントです。実際に発生したエラーとその解決策を含めています。

---

## 📋 目次

1. [概要](#概要)
2. [事前準備](#事前準備)
3. [音声データ準備](#音声データ準備)
4. [メタデータ作成](#メタデータ作成)
5. [学習設定ファイル](#学習設定ファイル)
6. [学習実行](#学習実行)
7. [発生したエラーと解決策](#発生したエラーと解決策)
8. [学習完了後の手順](#学習完了後の手順)
9. [トラブルシューティング](#トラブルシューティング)
10. [よくある質問](#よくある質問)

---

## 🎯 概要

### CosyVoice LoRAファインチューニングとは

LoRA（Low-Rank Adaptation）は、大規模な事前学習モデルを少量のパラメータで特定の話者に適応させる手法です。CosyVoiceでは、あなたの声データでLoRAファインチューニングを行うことで、高品質な音声合成が可能になります。

### 必要な時間とリソース

| 項目 | 最小要件 | 推奨 |
|-----|---------|------|
| **GPU** | NVIDIA RTX 3060 | RTX 3080以上 |
| **VRAM** | 6-8GB | 12GB以上 |
| **RAM** | 16GB | 32GB以上 |
| **ストレージ** | 20GB | 50GB以上 |
| **学習時間** | 1.5-2時間 | 1時間 |
| **音声データ** | 200サンプル | 300サンプル以上 |

---

## 🔧 事前準備

### 1. 環境構築

```bash
# Python 3.10環境
conda create -n cosyvoice python=3.10
conda activate cosyvoice

# CosyVoiceインストール
cd /path/to/CosyVoice
pip install -r requirements.txt
```

### 2. プリトレインモデルのダウンロード

```
pretrained_models/CosyVoice2-0.5B/
├── campplus.onnx               # 話者埋め込み抽出（必須）
├── speech_tokenizer_v2.onnx    # 音声トークン抽出（必須）
├── llm.pt                      # LLM事前学習モデル（必須）
├── flow.pt                     # フローモデル（必須）
├── hift.pt                     # ボコーダー（必須）
└── CosyVoice-BlankEN/          # Qwenモデル（オプション）
    ├── config.json
    └── model.safetensors
```

**重要**: `CosyVoice-BlankEN`がなくても学習は可能です。ただし、ある場合は品質が向上する可能性があります。

### 3. ディレクトリ構造

```
lora_yotaro/                     # 話者名に応じて変更
├── segments/                    # 分割済み音声ファイル
│   ├── yotaro_0001.wav
│   ├── yotaro_0002.wav
│   └── ... (200-300個推奨)
├── wav.scp                      # 音声ファイルリスト
├── text                         # 書き起こしテキスト
├── utt2spk                      # 発話→話者マッピング
├── spk2utt                      # 話者→発話マッピング
├── lora_config.json            # LoRA設定
├── train_lora_lowmem.yaml      # 低メモリ版学習設定
├── wsl_finetune_lora_lowmem.sh # 学習実行スクリプト
└── transfer_to_wsl_http.sh     # 転送スクリプト（Mac→WSL）
```

---

## 🎤 音声データ準備

### データ量と品質の目安

| サンプル数 | 総時間 | 学習時間 | 品質 | 推奨度 |
|-----------|--------|---------|------|--------|
| 50-100個 | 5-10分 | 30分 | ⭐⭐ | テスト用 |
| 100-200個 | 10-20分 | 1時間 | ⭐⭐⭐ | 最低限 |
| **200-300個** | **20-30分** | **1.5時間** | **⭐⭐⭐⭐** | **推奨** |
| 500個以上 | 50分以上 | 3時間+ | ⭐⭐⭐⭐⭐ | 最高品質 |

### 音声ファイルの要件

✅ **必須条件**:
- **サンプリングレート**: 24000Hz
- **フォーマット**: WAV形式
- **ビット深度**: 16bit
- **チャンネル**: モノラル（1ch）
- **長さ**: 3-10秒/ファイル
- **ノイズ**: 最小限
- **話者**: 単一話者のみ

❌ **避けるべき**:
- BGM入り音声
- 複数人の会話
- エコー・リバーブが強い音声
- 極端に短い（1秒未満）または長い（15秒以上）
- ノイズが多い音声
- 音量が極端に小さいまたは大きい

### 音声データの準備スクリプト

```bash
#!/bin/bash
# prepare_audio_data.sh
# 長い音声ファイルを3-10秒のセグメントに分割

SPEAKER="yotaro"
INPUT_AUDIO="yotaro_voice_long.wav"
OUTPUT_DIR="lora_${SPEAKER}/segments"

mkdir -p "${OUTPUT_DIR}"

# pydubを使って分割
python3 << 'EOF'
from pydub import AudioSegment
from pydub.silence import split_on_silence
import os
import sys

SPEAKER = os.environ['SPEAKER']
INPUT_AUDIO = os.environ['INPUT_AUDIO']
OUTPUT_DIR = os.environ['OUTPUT_DIR']

print(f"音声ファイル読み込み: {INPUT_AUDIO}")
audio = AudioSegment.from_wav(INPUT_AUDIO)

# 24000Hzに変換
audio = audio.set_frame_rate(24000).set_channels(1)

print("無音部分で分割中...")
segments = split_on_silence(
    audio,
    min_silence_len=500,    # 500ms以上の無音
    silence_thresh=-40,     # -40dB以下を無音とみなす
    keep_silence=200        # 前後200ms残す
)

print(f"分割完了: {len(segments)}個のセグメント")

# 3-10秒のセグメントのみ保存
count = 0
for i, segment in enumerate(segments):
    duration = len(segment) / 1000.0  # 秒
    if 3.0 <= duration <= 10.0:
        count += 1
        filename = f"{OUTPUT_DIR}/{SPEAKER}_{count:04d}.wav"
        segment.export(filename, format="wav")
        print(f"  保存: {filename} ({duration:.2f}秒)")

print(f"\n✅ {count}個のセグメント保存完了")
EOF
```

---

## 📝 メタデータ作成

### 1. wav.scp（音声ファイルリスト）

各行に `発話ID<スペース>音声ファイルのフルパス` を記述：

```
yotaro_0001 /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro/segments/yotaro_0001.wav
yotaro_0002 /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro/segments/yotaro_0002.wav
yotaro_0003 /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro/segments/yotaro_0003.wav
```

### 2. text（書き起こしテキスト）

各行に `発話ID<TAB>書き起こしテキスト` を記述：

```
yotaro_0001	はじめまして成沢木怜です
yotaro_0002	今日はいい天気ですね
yotaro_0003	音声合成技術について説明します
```

**重要**: 
- タブ区切りを使用（スペースではない）
- 書き起こしは正確に
- 句読点も含める

### 3. utt2spk（発話→話者マッピング）

各行に `発話ID<スペース>話者ID` を記述：

```
yotaro_0001 yotaro
yotaro_0002 yotaro
yotaro_0003 yotaro
```

### 4. spk2utt（話者→発話マッピング）

1行に `話者ID<スペース>全ての発話ID` を記述：

```
yotaro yotaro_0001 yotaro_0002 yotaro_0003 yotaro_0004 ...
```

### メタデータ作成スクリプト

```python
#!/usr/bin/env python3
# create_metadata.py

import os
import json
from pathlib import Path

SPEAKER = "yotaro"
DATA_DIR = f"lora_{SPEAKER}"
SEGMENTS_DIR = f"{DATA_DIR}/segments"

# 音声ファイル一覧取得
wav_files = sorted(Path(SEGMENTS_DIR).glob("*.wav"))
print(f"音声ファイル数: {len(wav_files)}")

# wav.scp作成
with open(f"{DATA_DIR}/wav.scp", "w") as f:
    for wav_file in wav_files:
        utt_id = wav_file.stem
        abs_path = wav_file.absolute()
        f.write(f"{utt_id} {abs_path}\n")
print("✅ wav.scp 作成完了")

# utt2spk作成
with open(f"{DATA_DIR}/utt2spk", "w") as f:
    for wav_file in wav_files:
        utt_id = wav_file.stem
        f.write(f"{utt_id} {SPEAKER}\n")
print("✅ utt2spk 作成完了")

# spk2utt作成
utt_ids = [f.stem for f in wav_files]
with open(f"{DATA_DIR}/spk2utt", "w") as f:
    f.write(f"{SPEAKER} " + " ".join(utt_ids) + "\n")
print("✅ spk2utt 作成完了")

# lora_config.json作成
config = {
    "speaker": SPEAKER,
    "num_samples": len(wav_files),
    "sample_rate": 24000,
    "training": {
        "epochs": 10,
        "batch_size": 2,
        "learning_rate": 1e-5,
        "gradient_accumulation": 8
    }
}
with open(f"{DATA_DIR}/lora_config.json", "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("✅ lora_config.json 作成完了")

print("\n⚠️  次に text ファイルを作成してください:")
print(f"   各行: utt_id<TAB>書き起こしテキスト")
print(f"   例: yotaro_0001<TAB>はじめまして成沢木怜です")
```

### text ファイルの作成（Whisper推奨）

```bash
# Whisperで自動書き起こし
pip install openai-whisper

python3 << 'EOF'
import whisper
from pathlib import Path

model = whisper.load_model("large-v3")
segments_dir = Path("lora_yotaro/segments")

with open("lora_yotaro/text", "w") as f:
    for wav_file in sorted(segments_dir.glob("*.wav")):
        result = model.transcribe(str(wav_file), language="ja")
        utt_id = wav_file.stem
        text = result["text"].strip()
        f.write(f"{utt_id}\t{text}\n")
        print(f"{utt_id}: {text}")
EOF
```

---

## ⚙️ 学習設定ファイル

### train_lora_lowmem.yaml（低メモリ版・推奨）

```yaml
# CosyVoice2 LoRA Fine-tuning Configuration (低メモリ版)
# 推奨GPU VRAM: 6-8GB
# 学習時間: 1.5-2時間 (300サンプル)

# データセット設定（メモリ最適化）
dataset_conf:
  filter_conf:
    max_length: 20480
    min_length: 50
    token_max_length: 400      # トークン長制限
    token_min_length: 1
  resample_conf:
    resample_rate: 24000
  speed_perturb: false           # データ拡張無効化（メモリ削減）
  fbank_conf:
    num_mel_bins: 80
    frame_shift: 10
    frame_length: 25
    dither: 1.0
  spec_aug: false                # スペクトログラム拡張無効化
  shuffle: true
  shuffle_conf:
    shuffle_size: 500            # 1000→500に削減
  sort: true
  sort_conf:
    sort_size: 500               # 1000→500に削減
  batch_conf:
    batch_type: dynamic
    max_frames_in_batch: 400     # ★最重要: 2000→400（80%削減）

# 学習設定（メモリ最適化）
train_conf:
  accum_grad: 8                  # ★最重要: 2→8（実質バッチサイズ1/4）
  grad_clip: 5.0
  max_epoch: 10
  log_interval: 10
  save_checkpoint_interval: 500
  keep_checkpoint_max: 10
  val_interval: 500

# オプティマイザ設定
optim: adam
optim_conf:
  lr: 0.00001                    # 学習率
  weight_decay: 0.01

# スケジューラ設定
scheduler: warmuplr
scheduler_conf:
  warmup_steps: 100              # 500→100に削減

# LLMモデル設定（LoRA）
llm: !new:cosyvoice.llm.llm.CosyVoiceLLM
  llm_input_size: 4096
  llm_output_size: 4096
  text_token_size: 151936
  speech_token_size: 4096
  length_normalized_loss: true
  lora_rank: 8                   # ★重要: 16→8（50%削減）
  lora_alpha: 16
  lora_dropout: 0.05
  llm_type: qwen2.5
  pretrain_path: !PLACEHOLDER
  use_flash_attn: false          # Flash Attention無効化（メモリ削減）

# 損失関数設定
loss: ce_loss
loss_conf:
  padding_idx: -1

# Flowモデル設定（学習しない）
flow: !new:cosyvoice.flow.flow.CosyVoiceFlow
  input_size: 512
  output_size: 80
  spk_embed_dim: 192
  encoder_type: transformer
  encoder_params:
    input_layer: linear
    num_blocks: 6
    linear_units: 2048
    dropout_rate: 0.1
    positional_dropout_rate: 0.1
    attention_dropout_rate: 0.0
    normalize_before: true
    use_flash_attn: false

# HiFTGANボコーダー設定（学習しない）
hift: !new:cosyvoice.hifigan.generator.HiFTGenerator
  in_channels: 80
  base_channels: 512
  nb_harmonics: 8
  sampling_rate: 24000
  nsf_alpha: 0.1
  nsf_sigma: 0.003
  nsf_voiced_threshold: 10
  upsample_rates: [8, 8]
  upsample_kernel_sizes: [16, 16]
  istft_params:
    n_fft: 16
    hop_len: 4
  resblock_kernel_sizes: [3, 7, 11]
  resblock_dilation_sizes: [[1, 3, 5], [1, 3, 5], [1, 3, 5]]
  source_resblock_kernel_sizes: [7, 11]
  source_resblock_dilation_sizes: [[1, 3, 5], [1, 3, 5]]
  lrelu_slope: 0.1
  audio_limit: 0.99
  f0_predictor: rmvpe
  discriminator_params:
    base_channels: 128
    max_channels: 512
    downsample_scales: [4, 4, 4]
    inner_channels: [32, 32, 16, 16]
```

### メモリ削減の効果

| 設定項目 | デフォルト | 低メモリ版 | メモリ削減効果 |
|---------|----------|-----------|-------------|
| `max_frames_in_batch` | 2000 | **400** | 🔽 **80%削減** |
| `accum_grad` | 2 | **8** | 🔽 **75%削減** |
| `lora_rank` | 16 | **8** | 🔽 50%削減 |
| `shuffle_size` | 1000 | **500** | 🔽 50%削減 |
| `num_workers` | 2 | **1** | 🔽 50%削減 |
| `prefetch` | 100 | **50** | 🔽 50%削減 |
| `use_flash_attn` | true | **false** | メモリ節約 |
| `speed_perturb` | true | **false** | 処理削減 |

**結果**: VRAM使用量 12GB → **6-8GB** (約50%削減) ✅

---

## 🚀 学習実行

### 学習実行スクリプト（WSL側）

```bash
#!/bin/bash
# wsl_finetune_lora_lowmem.sh
# WSL側でLoRA学習を実行するスクリプト（低メモリ版）
# 実行場所: /mnt/c/Users/fhoshina/development/CosyVoice/
# 推奨GPU VRAM: 6-8GB

set -e

SPEAKER="yotaro"
DATA_DIR="/mnt/c/Users/fhoshina/development/CosyVoice/lora_${SPEAKER}"
COSYVOICE_DIR="/mnt/c/Users/fhoshina/development/CosyVoice"
PRETRAINED_MODEL="${COSYVOICE_DIR}/pretrained_models/CosyVoice2-0.5B"
OUTPUT_DIR="${COSYVOICE_DIR}/lora_${SPEAKER}_trained"
QWEN_PRETRAIN_PATH="${PRETRAINED_MODEL}/CosyVoice-BlankEN"

echo "=========================================="
echo "=== CosyVoice LoRA Fine-tuning ==="
echo "=== 低メモリ版（6-8GB VRAM） ==="
echo "=========================================="

cd ${COSYVOICE_DIR}
export PYTHONPATH="${COSYVOICE_DIR}:${PYTHONPATH}"

# GPUメモリ最適化の環境変数
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:128"
export CUDA_LAUNCH_BLOCKING=0

# Step 1: 話者埋め込み抽出
echo "Step 1/4: 話者埋め込み抽出..."
python tools/extract_embedding.py \
    --dir ${DATA_DIR} \
    --onnx_path ${PRETRAINED_MODEL}/campplus.onnx \
    --num_thread 4

# Step 2: 音声トークン抽出
echo "Step 2/4: 音声トークン抽出..."
python tools/extract_speech_token.py \
    --dir ${DATA_DIR} \
    --onnx_path ${PRETRAINED_MODEL}/speech_tokenizer_v2.onnx \
    --num_thread 4

# Step 3: Parquetファイル作成
echo "Step 3/4: Parquetファイル作成..."
mkdir -p ${DATA_DIR}/parquet
python tools/make_parquet_list.py \
    --num_utts_per_parquet 50 \
    --num_processes 2 \
    --src_dir ${DATA_DIR} \
    --des_dir ${DATA_DIR}/parquet

# Step 4: LoRAファインチューニング
echo "Step 4/4: LoRAファインチューニング..."
mkdir -p ${OUTPUT_DIR}
mkdir -p ${OUTPUT_DIR}/tensorboard

export CUDA_VISIBLE_DEVICES="0"
num_gpus=1
job_id=1986
num_workers=1
prefetch=50

# Qwen引数の処理
if [ -d "${QWEN_PRETRAIN_PATH}" ]; then
    QWEN_ARG="--qwen_pretrain_path ${QWEN_PRETRAIN_PATH}"
else
    QWEN_ARG=""
fi

# 学習実行
torchrun \
    --nnodes=1 \
    --nproc_per_node=${num_gpus} \
    --rdzv_id=${job_id} \
    --rdzv_backend="c10d" \
    --rdzv_endpoint="localhost:0" \
    cosyvoice/bin/train.py \
    --train_engine torch_ddp \
    --config ${DATA_DIR}/train_lora_lowmem.yaml \
    --train_data ${DATA_DIR}/parquet/data.list \
    --cv_data ${DATA_DIR}/parquet/data.list \
    ${QWEN_ARG} \
    --model llm \
    --checkpoint ${PRETRAINED_MODEL}/llm.pt \
    --model_dir ${OUTPUT_DIR} \
    --tensorboard_dir ${OUTPUT_DIR}/tensorboard \
    --ddp.dist_backend nccl \
    --num_workers ${num_workers} \
    --prefetch ${prefetch} \
    --pin_memory

echo "✅ LoRA学習完了！"
```

### 実行手順

```bash
# WSL側で学習実行
ssh fhoshina@100.125.179.5
cd /mnt/c/Users/fhoshina/development/CosyVoice
bash lora_yotaro/wsl_finetune_lora_lowmem.sh
```

### 学習進捗の確認

```bash
# 別ターミナルでリアルタイム監視
tail -f /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro_trained/train.log
```

---

## 🐛 発生したエラーと解決策

### エラー1: `HFValidationError: Repo id must use alphanumeric chars`

**エラーメッセージ**:
```
huggingface_hub.errors.HFValidationError: Repo id must use alphanumeric chars or '-', '_', '.', '--' and '..' are forbidden, '-' and '.' cannot start or end the name, max length is 96: ''.
```

**原因**: 
- `qwen_pretrain_path`が空文字列`""`として渡されている
- Hugging FaceがリポジトリIDとして解釈し、検証エラー

**解決策**:
```bash
# Qwenモデルがない場合は引数自体を渡さない
if [ -n "${QWEN_PRETRAIN_PATH}" ] && [ -d "${QWEN_PRETRAIN_PATH}" ]; then
    QWEN_ARG="--qwen_pretrain_path ${QWEN_PRETRAIN_PATH}"
else
    QWEN_ARG=""  # 空文字列ではなく、引数自体を省略
fi

torchrun ... ${QWEN_ARG} ...  # 空の場合は引数が展開されない
```

---

### エラー2: `KeyError: "Override 'hifigan' not found in config"`

**エラーメッセージ**:
```
omegaconf.errors.ConfigKeyError: Key 'hifigan' is not in struct
```

**原因**:
- 自作YAMLに`hifigan`セクションがない
- LLM学習では不要なセクション

**解決策**:
```bash
# 公式の cosyvoice2.yaml をそのまま使用
cp ${COSYVOICE_DIR}/examples/libritts/cosyvoice2/conf/cosyvoice2.yaml \
   ${DATA_DIR}/train_lora_lowmem.yaml
```

**教訓**: 公式設定をベースに、必要な部分だけオーバーライドする

---

### エラー3: `CUDA out of memory`

**エラーメッセージ**:
```
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 732.00 MiB. GPU
```

**原因**:
- デフォルト設定がVRAM 12GB以上を想定
- RTX 3060（12GB）でもギリギリまたは不足

**解決策**:

#### 1. YAMLでメモリ削減（最も効果的）

```yaml
# train_lora_lowmem.yaml
dataset_conf:
  batch_conf:
    max_frames_in_batch: 400  # 2000→400（80%削減）

train_conf:
  accum_grad: 8  # 2→8（実質バッチサイズ1/4）

llm:
  lora_rank: 8  # 16→8（50%削減）
  use_flash_attn: false  # メモリ節約
```

#### 2. 環境変数でメモリ最適化

```bash
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:128"
export CUDA_LAUNCH_BLOCKING=0
```

**結果**: VRAM使用量 12GB → **6-8GB** ✅

---

### エラー4: `libcublasLt.so.11: cannot open shared object file`

**エラーメッセージ**:
```
[E:onnxruntime:Default] Failed to load library libonnxruntime_providers_cuda.so with error: libcublasLt.so.11: cannot open shared object file: No such file or directory
```

**原因**:
- ONNXRuntimeのCUDAプロバイダーライブラリが見つからない

**影響**:
- ONNXRuntimeがCPUで動作
- **PyTorchのCUDAは正常動作**
- 学習には影響なし

**対応**:
```bash
# 警告を無視してOK
# Step 2の処理時間が若干長くなるが問題なし
```

---

### エラー5: `find_unused_parameters=True` 警告

**警告メッセージ**:
```
[W reducer.cpp:1389] Warning: find_unused_parameters=True was specified in DDP constructor, but did not find any unused parameters in the forward pass.
```

**影響**:
- パフォーマンスがわずかに低下
- **学習結果には影響なし**

**対応**: **警告を無視してOK**

---

## 📊 学習完了後の手順

### 1. 学習済みモデルの確認

```bash
# WSL側
cd /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro_trained
ls -lh *.pt

# 期待されるファイル:
# - init.pt (初期化時)
# - epoch_0_whole.pt
# - epoch_1_whole.pt
# - ...
# - epoch_9_whole.pt
```

### 2. ベストモデルの選択

```bash
# 最終エポックを使用（通常これが最良）
cd /mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro_trained
cp epoch_9_whole.pt final_lora_model.pt
```

### 3. Mac側に転送

```bash
# Mac側で実行
scp fhoshina@100.125.179.5:/mnt/c/Users/fhoshina/development/CosyVoice/lora_yotaro_trained/final_lora_model.pt \
    lora_yotaro/
```

### 4. speakers_config.json に設定追加

```json
{
  "yotaro": {
    "reference_audio": "reference_voice_24k.wav",
    "long_audio": "yotaro_voice_long.wav",
    "prompt_text": "はじめまして成沢木怜です",
    "lora_model": "lora_yotaro/final_lora_model.pt",
    "active": true
  }
}
```

---

## 🔍 トラブルシューティング

### Q: 学習が途中で止まる

**確認事項**:
```bash
# GPUメモリ確認
nvidia-smi

# プロセス確認
ps aux | grep python

# ログ確認
tail -f lora_yotaro_trained/train.log
```

### Q: Loss が減少しない

**対処法**:
```yaml
# train_lora_lowmem.yaml
optim_conf:
  lr: 0.000005  # 学習率を下げる
  
train_conf:
  max_epoch: 20  # エポック数を増やす
```

### Q: VRAM不足が解決しない

**対処法**:
```yaml
# さらにメモリ削減
train_conf:
  accum_grad: 16          # 8→16
  max_frames_in_batch: 200  # 400→200

llm:
  lora_rank: 4  # 8→4
```

---

## ❓ よくある質問

### Q: Qwenモデルは必須ですか？

**A**: いいえ、オプションです。なくても学習可能です。

### Q: 学習時間を短縮できますか？

**A**: はい、以下の方法があります：
1. エポック数を減らす（10 → 5）
2. サンプル数を減らす（300 → 150）
3. より高性能なGPUを使用

### Q: 複数の話者を学習できますか？

**A**: はい、話者ごとに別々のLoRAモデルを学習します。

### Q: 学習データの推奨量は？

**A**: 
- 最小: 100サンプル（約10分）
- **推奨: 200-300サンプル（20-30分）**
- 最良: 500サンプル以上（50分以上）

---

## 📈 学習時間の目安

| サンプル数 | GPU | 推定時間/エポック | 10エポック |
|-----------|-----|----------------|-----------|
| 100個 | RTX 3060 | 5分 | 50分 |
| 200個 | RTX 3060 | 7分 | 70分 |
| **298個** | **RTX 3060** | **9分** | **90分** |
| 500個 | RTX 3060 | 15分 | 150分 |

**実績**:
- サンプル数: 298個
- GPU: RTX 3060 12GB
- **推定総時間**: 約1.5時間 ✅

---

## ✅ 成功のチェックリスト

### 準備段階
- [ ] Python 3.10環境構築
- [ ] CosyVoiceインストール
- [ ] プリトレインモデル配置
- [ ] 音声データ: 200個以上、3-10秒/ファイル
- [ ] メタデータファイル作成完了
- [ ] `train_lora_lowmem.yaml`配置

### 実行段階
- [ ] Step 1: 話者埋め込み抽出が完了
- [ ] Step 2: 音声トークン抽出が完了
- [ ] Step 3: Parquetファイルが生成
- [ ] Step 4: 学習開始が確認できる
- [ ] メモリエラーが発生しない
- [ ] Loss が減少傾向

### 完了後
- [ ] チェックポイントが複数生成
- [ ] Mac側に転送完了
- [ ] `speakers_config.json`設定完了
- [ ] テスト音声生成で品質確認

---

## 🎓 重要ポイントまとめ

### 1. メモリ最適化が成功の鍵
```yaml
max_frames_in_batch: 400    # 80%削減
accum_grad: 8               # 75%削減
lora_rank: 8                # 50%削減
```

### 2. 公式設定をベースにする
- YAMLを自作せず、公式をベース
- 必要な部分だけオーバーライド

### 3. 警告の見極め
- ONNXRuntimeの警告 → 無視OK ✅
- `find_unused_parameters` → 無視OK ✅
- `CUDA out of memory` → 対応必須 ❌

### 4. データ品質 > データ量
- 300個の高品質データ > 1000個のノイジーデータ

### 5. 環境変数でメモリ最適化
```bash
export PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:128"
```

---

**おめでとうございます！これでCosyVoice LoRAファインチューニングは完璧です！** 🎊🚀
