#!/usr/bin/env python3
"""
generate_metadata.py
学習用メタデータファイル（utt2spk, spk2utt, wav.scp）を生成

使い方:
    python3 generate_metadata.py
"""

from pathlib import Path

# 設定
SPEAKER_ID = "narisawa2"  # 話者ID
DATA_DIR = Path(__file__).parent
SEGMENTS_DIR = DATA_DIR / "segments"
TEXT_FILE = DATA_DIR / "text"

# 出力ファイル
UTT2SPK_FILE = DATA_DIR / "utt2spk"
SPK2UTT_FILE = DATA_DIR / "spk2utt"
WAV_SCP_FILE = DATA_DIR / "wav.scp"

print("=" * 60)
print("📝 学習用メタデータファイル生成")
print("=" * 60)
print()

# textファイルから発話IDを取得
if not TEXT_FILE.exists():
    print(f"❌ エラー: textファイルが見つかりません: {TEXT_FILE}")
    exit(1)

utterance_ids = []
with open(TEXT_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            utt_id = line.split()[0]
            utterance_ids.append(utt_id)

print(f"📂 発話ID: {len(utterance_ids)}個")
print()

# 1. utt2spk生成（発話ID → 話者ID）
print("📝 utt2spk生成中...")
with open(UTT2SPK_FILE, "w", encoding="utf-8") as f:
    for utt_id in utterance_ids:
        f.write(f"{utt_id} {SPEAKER_ID}\n")
print(f"✅ {UTT2SPK_FILE.name} 生成完了 ({len(utterance_ids)}行)")

# 2. spk2utt生成（話者ID → 発話IDリスト）
print("📝 spk2utt生成中...")
with open(SPK2UTT_FILE, "w", encoding="utf-8") as f:
    f.write(f"{SPEAKER_ID} " + " ".join(utterance_ids) + "\n")
print(f"✅ {SPK2UTT_FILE.name} 生成完了")

# 3. wav.scp生成（発話ID → WAVファイル絶対パス）
# WSL側のパスを想定: /mnt/c/Users/fhoshina/development/CosyVoice/lora_narisawa2/segments/segment_XXXX.wav
print("📝 wav.scp生成中...")

# WSL側の絶対パスを生成
wsl_base_path = "/mnt/c/Users/fhoshina/development/CosyVoice/lora_narisawa2"

with open(WAV_SCP_FILE, "w", encoding="utf-8") as f:
    for utt_id in utterance_ids:
        # segment_0001 → segment_0001.wav
        wav_filename = f"{utt_id}.wav"
        wsl_wav_path = f"{wsl_base_path}/segments/{wav_filename}"
        f.write(f"{utt_id} {wsl_wav_path}\n")

print(f"✅ {WAV_SCP_FILE.name} 生成完了 ({len(utterance_ids)}行)")
print()

# 検証
print("🔍 生成ファイル検証:")
print(f"   - {UTT2SPK_FILE.name}: {UTT2SPK_FILE.stat().st_size} bytes")
print(f"   - {SPK2UTT_FILE.name}: {SPK2UTT_FILE.stat().st_size} bytes")
print(f"   - {WAV_SCP_FILE.name}: {WAV_SCP_FILE.stat().st_size} bytes")
print()

# サンプル表示
print("📄 サンプル (utt2spk):")
with open(UTT2SPK_FILE, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i < 3:
            print(f"   {line.strip()}")
        else:
            break

print()
print("📄 サンプル (spk2utt):")
with open(SPK2UTT_FILE, "r", encoding="utf-8") as f:
    content = f.read().strip()
    if len(content) > 100:
        print(f"   {content[:100]}...")
    else:
        print(f"   {content}")

print()
print("📄 サンプル (wav.scp):")
with open(WAV_SCP_FILE, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i < 3:
            print(f"   {line.strip()}")
        else:
            break

print()
print("=" * 60)
print("✅ メタデータファイル生成完了！")
print("=" * 60)
print()
print("📊 統計:")
print(f"   - 発話数: {len(utterance_ids)}")
print(f"   - 話者ID: {SPEAKER_ID}")
print(f"   - WSLパス: {wsl_base_path}")
print()
print("🎯 次のステップ:")
print("   1. Mac側のファイルをWSL側に転送")
print("   2. WSL側でLoRA学習実行")
print()
