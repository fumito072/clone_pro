#!/usr/bin/env python3
"""
長尺音声ファイルを3-5秒のセグメントに分割するスクリプト
Usage: python split_audio_to_segments.py <input_wav> [--min-duration 3] [--max-duration 5]
"""

import argparse
import wave
import numpy as np
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import detect_nonsilent


def split_audio_by_silence(input_path: str, output_dir: str, min_segment_ms: int = 3000, 
                           max_segment_ms: int = 5000, silence_thresh: int = -40):
    """
    音声ファイルを無音区間で分割し、3-5秒のセグメントに切り出す
    
    Args:
        input_path: 入力WAVファイルパス
        output_dir: 出力ディレクトリ
        min_segment_ms: 最小セグメント長（ミリ秒）
        max_segment_ms: 最大セグメント長（ミリ秒）
        silence_thresh: 無音判定の閾値（dBFS）
    """
    print(f"📂 入力ファイル: {input_path}")
    print(f"📁 出力先: {output_dir}")
    
    # 音声ファイル読み込み
    audio = AudioSegment.from_wav(input_path)
    duration_sec = len(audio) / 1000.0
    print(f"⏱️  元音声の長さ: {duration_sec:.2f}秒 ({duration_sec/60:.2f}分)")
    
    # 無音でない区間を検出（最小無音長200ms）
    print(f"🔍 無音区間を検出中... (閾値: {silence_thresh}dBFS)")
    nonsilent_ranges = detect_nonsilent(
        audio, 
        min_silence_len=200,  # 200ms以上の無音を区切りとする
        silence_thresh=silence_thresh,
        seek_step=10  # 10msステップでスキャン
    )
    
    print(f"✅ {len(nonsilent_ranges)}個の発話区間を検出")
    
    # セグメント分割: 各発話区間を最大長で切り出す
    segments = []
    
    for i, (start_ms, end_ms) in enumerate(nonsilent_ranges):
        chunk_duration = end_ms - start_ms
        
        # 短すぎる区間はスキップ（1秒未満）
        if chunk_duration < 1000:
            continue
        
        # 最大長以下なら、そのまま1セグメント
        if chunk_duration <= max_segment_ms:
            if chunk_duration >= min_segment_ms:
                segments.append({"start": start_ms, "end": end_ms})
        else:
            # 最大長を超える場合、max_segment_ms単位で分割
            current_pos = start_ms
            while current_pos < end_ms:
                next_pos = min(current_pos + max_segment_ms, end_ms)
                seg_duration = next_pos - current_pos
                
                # 最小長以上なら追加
                if seg_duration >= min_segment_ms:
                    segments.append({"start": current_pos, "end": next_pos})
                
                current_pos = next_pos
    
    print(f"📦 {len(segments)}個のセグメントを生成 ({min_segment_ms/1000}-{max_segment_ms/1000}秒)")
    
    # セグメントをファイルに保存
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for idx, seg in enumerate(segments):
        segment_audio = audio[seg["start"]:seg["end"]]
        duration_sec = len(segment_audio) / 1000.0
        
        # ファイル名: segment_0001.wav, segment_0002.wav, ...
        filename = f"segment_{idx+1:04d}.wav"
        filepath = output_path / filename
        
        # WAV形式で保存（24kHz, mono推奨）
        segment_audio = segment_audio.set_frame_rate(24000).set_channels(1)
        segment_audio.export(filepath, format="wav")
        
        print(f"  ✅ {filename} ({duration_sec:.2f}秒)")
    
    print(f"\n🎉 完了！ {len(segments)}個のセグメントを {output_dir} に保存しました")
    
    # 統計情報
    durations = [(seg["end"] - seg["start"]) / 1000.0 for seg in segments]
    avg_duration = np.mean(durations)
    total_duration = sum(durations)
    
    print(f"\n📊 統計:")
    print(f"   - 総セグメント時間: {total_duration:.2f}秒 ({total_duration/60:.2f}分)")
    print(f"   - 平均セグメント長: {avg_duration:.2f}秒")
    print(f"   - 最短セグメント: {min(durations):.2f}秒")
    print(f"   - 最長セグメント: {max(durations):.2f}秒")
    print(f"   - カバー率: {total_duration/duration_sec*100:.1f}% (元音声に対する比率)")


def main():
    parser = argparse.ArgumentParser(description="音声ファイルを3-5秒のセグメントに分割")
    parser.add_argument("input_wav", help="入力WAVファイルパス")
    parser.add_argument("--output-dir", default="segments", help="出力ディレクトリ (デフォルト: segments)")
    parser.add_argument("--min-duration", type=float, default=3.0, help="最小セグメント長（秒）")
    parser.add_argument("--max-duration", type=float, default=5.0, help="最大セグメント長（秒）")
    parser.add_argument("--silence-thresh", type=int, default=-40, help="無音判定閾値 (dBFS)")
    
    args = parser.parse_args()
    
    # 入力ファイルチェック
    if not Path(args.input_wav).exists():
        print(f"❌ エラー: ファイルが見つかりません: {args.input_wav}")
        return 1
    
    # 分割実行
    split_audio_by_silence(
        input_path=args.input_wav,
        output_dir=args.output_dir,
        min_segment_ms=int(args.min_duration * 1000),
        max_segment_ms=int(args.max_duration * 1000),
        silence_thresh=args.silence_thresh
    )
    
    return 0


if __name__ == "__main__":
    exit(main())
