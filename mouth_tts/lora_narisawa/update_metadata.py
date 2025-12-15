#!/usr/bin/env python3
"""
update_metadata.py
segments内の全WAVファイルからメタデータファイル（wav.scp, utt2spk, spk2utt）を再生成

使い方:
    python3 update_metadata.py
"""

import os
from pathlib import Path

# 設定
SPEAKER = "narisawa"
DATA_DIR = Path(__file__).parent
SEGMENTS_DIR = DATA_DIR / "segments"
WSL_BASE_PATH = f"/mnt/c/Users/fhoshina/development/CosyVoice/lora_{SPEAKER}"

print("=" * 60)
print("📝 メタデータファイル更新")
print("=" * 60)
print()

# segments内の全WAVファイルを取得
wav_files = sorted(SEGMENTS_DIR.glob(f"{SPEAKER}_segment_*.wav"))
print(f"📂 音声ファイル数: {len(wav_files)}個")
print()

if not wav_files:
    print("❌ segments内にWAVファイルが見つかりません")
    exit(1)

# 1. wav.scp作成
print("📄 wav.scp 作成中...")
with open(DATA_DIR / "wav.scp", "w") as f:
    for wav_file in wav_files:
        utt_id = wav_file.stem
        wsl_path = f"{WSL_BASE_PATH}/segments/{wav_file.name}"
        f.write(f"{utt_id} {wsl_path}\n")

print(f"✅ wav.scp 作成完了（{len(wav_files)}行）")
print(f"   例: {wav_files[0].stem} {WSL_BASE_PATH}/segments/{wav_files[0].name}")
print()

# 2. utt2spk作成
print("📄 utt2spk 作成中...")
with open(DATA_DIR / "utt2spk", "w") as f:
    for wav_file in wav_files:
        utt_id = wav_file.stem
        f.write(f"{utt_id} {SPEAKER}\n")

print(f"✅ utt2spk 作成完了（{len(wav_files)}行）")
print()

# 3. spk2utt作成
print("📄 spk2utt 作成中...")
utt_ids = [f.stem for f in wav_files]
with open(DATA_DIR / "spk2utt", "w") as f:
    f.write(f"{SPEAKER} " + " ".join(utt_ids) + "\n")

print(f"✅ spk2utt 作成完了（1行、{len(utt_ids)}個の発話ID）")
print()

# 4. text ファイルのチェック
text_file = DATA_DIR / "text"
if text_file.exists():
    with open(text_file, "r") as f:
        text_lines = [line.strip() for line in f if line.strip()]
    
    existing_utts = set(line.split()[0] for line in text_lines if line)
    all_utts = set(utt_ids)
    missing_utts = all_utts - existing_utts
    
    if missing_utts:
        print("⚠️  text ファイルに不足している発話ID:")
        for utt in sorted(missing_utts)[:10]:  # 最初の10個だけ表示
            print(f"   - {utt}")
        if len(missing_utts) > 10:
            print(f"   ... 他 {len(missing_utts) - 10}個")
        print()
        print("📝 これらの発話IDに対して文字起こしを追加してください")
        print(f"   形式: <発話ID><TAB><テキスト>")
        print(f"   例: {list(missing_utts)[0]}\tここに文字起こしテキスト")
        print()
    else:
        print("✅ text ファイル: 全ての発話IDに対応しています")
        print()
else:
    print("⚠️  text ファイルが見つかりません")
    print("   各セグメントの文字起こしを作成してください")
    print()

print("=" * 60)
print("✅ メタデータファイル更新完了！")
print("=" * 60)
print()
print("📊 統計:")
print(f"   - 音声ファイル: {len(wav_files)}個")
print(f"   - wav.scp: {len(wav_files)}行")
print(f"   - utt2spk: {len(wav_files)}行")
print(f"   - spk2utt: 1行（{len(utt_ids)}個の発話ID）")
print()
print("🎯 次のステップ:")
if text_file.exists() and missing_utts:
    print("   1. text ファイルに不足している文字起こしを追加")
    print("   2. WSL側に転送:")
    print("      bash transfer_to_wsl_http.sh")
else:
    print("   1. WSL側に転送:")
    print("      bash transfer_to_wsl_http.sh")
print()
