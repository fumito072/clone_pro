"""
新規話者の音声データ準備スクリプト

M4A/MP3などの音声ファイルをWAVに変換し、
セグメント分割、Google Cloud文字起こし、
メタデータ生成まで一括で実行します。
"""

import argparse
import subprocess
from pathlib import Path
import torchaudio
import torch
from tqdm import tqdm
import os
from google.cloud import speech_v1p1beta1 as speech
import time


def convert_to_wav(input_file, output_file, target_sr=24000):
    """
    音声ファイルをWAV形式に変換
    """
    print(f"\n🔄 WAV変換中: {input_file.name}")
    
    try:
        # ffmpegで変換
        cmd = [
            'ffmpeg',
            '-i', str(input_file),
            '-ar', str(target_sr),
            '-ac', '1',
            '-c:a', 'pcm_s16le',
            '-y',
            str(output_file)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ WAV変換完了: {output_file}")
            return True
        else:
            print(f"❌ 変換失敗: {result.stderr}")
            return False
    
    except FileNotFoundError:
        print("❌ ffmpegが見つかりません")
        print("💡 インストール: brew install ffmpeg")
        return False


def split_audio_into_segments(audio_file, output_dir, speaker_name, segment_length=10.0, sample_rate=24000):
    """
    音声を固定長セグメントに分割
    """
    print(f"\n✂️  音声セグメント分割中...")
    
    # 音声読み込み
    waveform, sr = torchaudio.load(str(audio_file))
    
    # サンプルレート確認
    if sr != sample_rate:
        resampler = torchaudio.transforms.Resample(sr, sample_rate)
        waveform = resampler(waveform)
        sr = sample_rate
    
    # モノラル変換
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)
    
    total_duration = waveform.shape[1] / sr
    segment_samples = int(segment_length * sr)
    
    print(f"   総音声長: {total_duration:.1f}秒")
    print(f"   セグメント長: {segment_length}秒")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    segment_count = 0
    for start_sample in range(0, waveform.shape[1], segment_samples):
        end_sample = min(start_sample + segment_samples, waveform.shape[1])
        segment = waveform[:, start_sample:end_sample]
        
        # 短すぎるセグメントはスキップ
        if segment.shape[1] < sr * 2:  # 2秒未満
            continue
        
        output_path = output_dir / f"{speaker_name}_segment_{segment_count:04d}.wav"
        torchaudio.save(str(output_path), segment, sr)
        segment_count += 1
    
    print(f"✅ セグメント分割完了: {segment_count}ファイル")
    return segment_count


def transcribe_with_google_cloud(segments_dir, speaker_name, output_file):
    """
    Google Cloud Speech-to-Textで文字起こし
    """
    print(f"\n📝 Google Cloud文字起こし開始...")
    
    segment_files = sorted(list(segments_dir.glob(f"{speaker_name}_segment_*.wav")))
    
    if len(segment_files) == 0:
        print("❌ セグメントファイルが見つかりません")
        return False
    
    # Google Cloud認証確認
    try:
        client = speech.SpeechClient()
        print("✅ Google Cloud認証成功")
    except Exception as e:
        print(f"❌ 認証失敗: {e}")
        return False
    
    transcriptions = []
    
    for audio_file in tqdm(segment_files, desc="文字起こし"):
        utt_id = audio_file.stem
        
        # 音声読み込み
        with open(audio_file, "rb") as f:
            content = f.read()
        
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=24000,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
            model="latest_long",
            use_enhanced=True,
        )
        
        try:
            response = client.recognize(config=config, audio=audio)
            
            transcript = ""
            for result in response.results:
                transcript += result.alternatives[0].transcript
            
            if transcript.strip():
                transcriptions.append({
                    "utt_id": utt_id,
                    "text": transcript.strip()
                })
        
        except Exception as e:
            print(f"\n⚠️  {audio_file.name}: {e}")
        
        time.sleep(0.1)  # API制限対策
    
    # textファイル出力
    with open(output_file, "w", encoding="utf-8") as f:
        for item in transcriptions:
            f.write(f"{item['utt_id']} {item['text']}\n")
    
    print(f"\n✅ 文字起こし完了: {len(transcriptions)}行")
    return True


def create_metadata_files(lora_dir, speaker_name):
    """
    メタデータファイル生成（wav.scp, utt2spk, spk2utt）
    """
    print(f"\n📄 メタデータファイル生成中...")
    
    segments_dir = lora_dir / "segments"
    segment_files = sorted(list(segments_dir.glob(f"{speaker_name}_segment_*.wav")))
    
    # wav.scp
    wav_scp = lora_dir / "wav.scp"
    with open(wav_scp, "w") as f:
        for audio_file in segment_files:
            f.write(f"{audio_file.stem} {audio_file.absolute()}\n")
    print(f"✅ wav.scp: {len(segment_files)}行")
    
    # utt2spk
    utt2spk = lora_dir / "utt2spk"
    with open(utt2spk, "w") as f:
        for audio_file in segment_files:
            f.write(f"{audio_file.stem} {speaker_name}\n")
    print(f"✅ utt2spk: {len(segment_files)}行")
    
    # spk2utt
    spk2utt = lora_dir / "spk2utt"
    with open(spk2utt, "w") as f:
        utt_ids = [audio_file.stem for audio_file in segment_files]
        f.write(f"{speaker_name} {' '.join(utt_ids)}\n")
    print(f"✅ spk2utt: 1行")
    
    # GCP用パス置換スクリプト
    replace_script = lora_dir / "replace_paths_for_gcp.sh"
    with open(replace_script, "w") as f:
        f.write(f"""#!/bin/bash
LORA_DIR="$HOME/lora_{speaker_name}"
sed -i.bak "s|{lora_dir}|${{LORA_DIR}}|g" ${{LORA_DIR}}/wav.scp
echo "✅ パス置換完了"
""")
    replace_script.chmod(0o755)
    print(f"✅ GCP用パス置換スクリプト生成")


def prepare_speaker_data(audio_file_path, speaker_name):
    """
    新規話者データの完全準備
    """
    print("\n" + "="*70)
    print(f"🎯 新規話者データ準備: {speaker_name}")
    print("="*70)
    
    base_dir = Path(__file__).parent
    audio_file = Path(audio_file_path)
    
    if not audio_file.exists():
        print(f"❌ 音声ファイルが見つかりません: {audio_file}")
        return False
    
    # LoRAディレクトリ作成
    lora_dir = base_dir / f"lora_{speaker_name}"
    lora_dir.mkdir(exist_ok=True)
    
    segments_dir = lora_dir / "segments"
    
    # WAV変換
    wav_file = lora_dir / f"{speaker_name}_source.wav"
    if audio_file.suffix.lower() != '.wav':
        if not convert_to_wav(audio_file, wav_file):
            return False
    else:
        wav_file = audio_file
    
    # セグメント分割
    segment_count = split_audio_into_segments(
        wav_file,
        segments_dir,
        speaker_name,
        segment_length=10.0
    )
    
    if segment_count == 0:
        print("❌ セグメント生成失敗")
        return False
    
    # Google Cloud文字起こし
    text_file = lora_dir / "text"
    if not transcribe_with_google_cloud(segments_dir, speaker_name, text_file):
        print("⚠️  文字起こし失敗（スキップ可能）")
    
    # メタデータ生成
    create_metadata_files(lora_dir, speaker_name)
    
    # サマリー
    print("\n" + "="*70)
    print("✅ データ準備完了！")
    print("="*70)
    
    print(f"\n📦 生成されたファイル:")
    print(f"   {lora_dir}/")
    print(f"   ├── segments/  ({segment_count}ファイル)")
    print(f"   ├── text")
    print(f"   ├── wav.scp")
    print(f"   ├── utt2spk")
    print(f"   └── spk2utt")
    
    # 次のステップ
    print(f"\n🎯 次のステップ:")
    print(f"\n1. データをtar.gzにまとめる:")
    print(f"   cd {base_dir}")
    print(f"   tar -czf lora_{speaker_name}.tar.gz lora_{speaker_name}/")
    
    print(f"\n2. Google Cloud VMにアップロード:")
    print(f"   gcloud compute scp lora_{speaker_name}.tar.gz cosyvoice-finetune:~/ --zone=us-central1-a")
    
    print(f"\n3. VM上でファインチューニング:")
    print(f"   bash gpu_finetune.sh")
    
    print("\n" + "="*70)
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="新規話者データ準備")
    parser.add_argument("--audio", type=str, required=True, help="音声ファイルパス")
    parser.add_argument("--speaker", type=str, required=True, help="話者名")
    parser.add_argument("--segment-length", type=float, default=10.0, help="セグメント長（秒）")
    
    args = parser.parse_args()
    
    # Google Cloud Project設定
    if "GOOGLE_CLOUD_PROJECT" not in os.environ:
        os.environ["GOOGLE_CLOUD_PROJECT"] = "president-clone-1762149165"
    
    prepare_speaker_data(args.audio, args.speaker)
