#!/usr/bin/env python3
"""
split_audio_to_segments.py
長い音声ファイルを10秒ごとに分割してsegmentsに追加

使い方:
    python3 split_audio_to_segments.py
"""

import os
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import split_on_silence

# 設定
SPEAKER = "narisawa"
DATA_DIR = Path(__file__).parent
INPUT_AUDIO = DATA_DIR / "narisawave_voice.wav"
SEGMENTS_DIR = DATA_DIR / "segments"
SEGMENT_LENGTH_MS = 10000  # 10秒 = 10000ミリ秒
MIN_SEGMENT_LENGTH_MS = 3000  # 最小3秒
MAX_SEGMENT_LENGTH_MS = 12000  # 最大12秒

# 既存のセグメント番号を取得
existing_segments = sorted(SEGMENTS_DIR.glob(f"{SPEAKER}_segment_*.wav"))
if existing_segments:
    last_segment = existing_segments[-1]
    last_num = int(last_segment.stem.split("_")[-1])
    start_num = last_num + 1
    print(f"📊 既存セグメント: {len(existing_segments)}個（最後: {last_segment.name}）")
else:
    start_num = 0
    print(f"📊 既存セグメント: なし")

print(f"🎬 新規セグメント開始番号: {SPEAKER}_segment_{start_num:04d}.wav")
print()

# 音声ファイル読み込み
print(f"📂 音声ファイル読み込み: {INPUT_AUDIO.name}")
if not INPUT_AUDIO.exists():
    print(f"❌ ファイルが見つかりません: {INPUT_AUDIO}")
    exit(1)

audio = AudioSegment.from_wav(INPUT_AUDIO)
print(f"✅ 読み込み完了")
print(f"   - 長さ: {len(audio) / 1000:.1f}秒")
print(f"   - サンプルレート: {audio.frame_rate}Hz")
print(f"   - チャンネル: {audio.channels}ch")
print()

# 24000Hz、モノラルに変換
print("🔧 音声を正規化中...")
audio = audio.set_frame_rate(24000).set_channels(1)
print(f"✅ 正規化完了: 24000Hz, モノラル")
print()

# 無音部分で分割（まず大まかに）
print("✂️  無音部分で分割中...")
chunks = split_on_silence(
    audio,
    min_silence_len=500,    # 500ms以上の無音
    silence_thresh=-40,     # -40dB以下を無音とみなす
    keep_silence=200        # 前後200ms残す
)
print(f"✅ {len(chunks)}個のチャンクに分割")
print()

# 各チャンクを10秒以下に分割
print("📏 10秒以下のセグメントに分割中...")
segments = []
for chunk in chunks:
    chunk_len = len(chunk)
    
    if chunk_len <= MAX_SEGMENT_LENGTH_MS:
        # 10秒以下ならそのまま
        if chunk_len >= MIN_SEGMENT_LENGTH_MS:
            segments.append(chunk)
    else:
        # 10秒を超える場合は分割
        num_splits = (chunk_len + SEGMENT_LENGTH_MS - 1) // SEGMENT_LENGTH_MS
        split_len = chunk_len // num_splits
        
        for i in range(num_splits):
            start = i * split_len
            end = start + split_len if i < num_splits - 1 else chunk_len
            segment = chunk[start:end]
            
            if len(segment) >= MIN_SEGMENT_LENGTH_MS:
                segments.append(segment)

print(f"✅ {len(segments)}個のセグメントに分割完了")
print()

# セグメントを保存
print("💾 セグメント保存中...")
saved_count = 0
for i, segment in enumerate(segments):
    segment_num = start_num + i
    filename = SEGMENTS_DIR / f"{SPEAKER}_segment_{segment_num:04d}.wav"
    
    duration_sec = len(segment) / 1000.0
    
    # 3秒以上12秒以下のセグメントのみ保存
    if MIN_SEGMENT_LENGTH_MS / 1000 <= duration_sec <= MAX_SEGMENT_LENGTH_MS / 1000:
        segment.export(filename, format="wav")
        saved_count += 1
        print(f"  ✅ {filename.name} ({duration_sec:.2f}秒)")
    else:
        print(f"  ⏭️  スキップ: {duration_sec:.2f}秒（範囲外）")

print()
print("=" * 60)
print(f"✅ 完了！{saved_count}個の新規セグメントを保存しました")
print("=" * 60)
print()
print(f"📊 統計:")
print(f"   - 既存セグメント: {len(existing_segments)}個")
print(f"   - 新規セグメント: {saved_count}個")
print(f"   - 合計セグメント: {len(existing_segments) + saved_count}個")
print()
print("🎯 次のステップ:")
print("   1. メタデータファイルを更新:")
print(f"      python3 update_metadata.py")
print()
