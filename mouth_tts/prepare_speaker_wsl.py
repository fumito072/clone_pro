"""
WSL用の新規話者データ準備スクリプト

macOSから送信された音声ファイルを処理し、
LoRAファインチューニング用のデータを準備します。

使い方:
    python3 prepare_speaker_wsl.py --audio ~/narisawa_voice.wav --speaker narisawa
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


def check_dependencies():
    """必要な依存関係をチェック"""
    print("🔍 依存関係チェック中...")
    
    # ffmpegチェック
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("✅ ffmpeg: インストール済み")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ffmpeg: 未インストール")
        print("💡 インストール: sudo apt-get install ffmpeg")
        return False
    
    # Google Cloud認証チェック
    try:
        client = speech.SpeechClient()
        print("✅ Google Cloud認証: OK")
    except Exception as e:
        print(f"⚠️  Google Cloud認証: {e}")
        print("💡 認証設定: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json")
    
    # PyTorchとtorchaudioチェック
    try:
        import torch
        import torchaudio
        print(f"✅ PyTorch: {torch.__version__}")
        print(f"✅ torchaudio: {torchaudio.__version__}")
    except ImportError as e:
        print(f"❌ PyTorch/torchaudio: {e}")
        return False
    
    return True


def convert_to_wav(input_file, output_file, target_sr=24000):
    """
    音声ファイルをWAV形式に変換（24kHz, モノラル）
    """
    print(f"\n🔄 WAV変換中: {input_file.name}")
    
    try:
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
    
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False


def split_audio_into_segments(audio_file, output_dir, speaker_name, segment_length=10.0, sample_rate=24000):
    """
    音声を固定長セグメントに分割
    
    Args:
        audio_file: 入力音声ファイル
        output_dir: 出力ディレクトリ
        speaker_name: 話者名
        segment_length: セグメント長（秒）
        sample_rate: サンプルレート
    
    Returns:
        生成されたセグメント数
    """
    print(f"\n✂️  音声セグメント分割中...")
    
    # 音声読み込み
    waveform, sr = torchaudio.load(str(audio_file))
    
    # リサンプリング
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
        
        # 短すぎるセグメントはスキップ（2秒未満）
        if segment.shape[1] < sr * 2:
            continue
        
        output_path = output_dir / f"{speaker_name}_segment_{segment_count:04d}.wav"
        torchaudio.save(str(output_path), segment, sr)
        segment_count += 1
    
    print(f"✅ セグメント分割完了: {segment_count}ファイル")
    return segment_count


def transcribe_with_google_cloud(segments_dir, speaker_name, output_file):
    """
    Google Cloud Speech-to-Textで文字起こし
    
    Args:
        segments_dir: セグメントディレクトリ
        speaker_name: 話者名
        output_file: 出力ファイルパス（text）
    
    Returns:
        成功したらTrue
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
        print("💡 GOOGLE_APPLICATION_CREDENTIALSを設定してください")
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
    LoRAトレーニング用メタデータファイル生成
    - wav.scp: 音声ファイルパスリスト
    - utt2spk: 発話→話者マッピング
    - spk2utt: 話者→発話リスト
    
    Args:
        lora_dir: LoRAディレクトリ
        speaker_name: 話者名
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


def prepare_speaker_data_wsl(audio_file_path, speaker_name, segment_length=10.0):
    """
    WSL用の新規話者データ準備（メイン処理）
    
    Args:
        audio_file_path: 入力音声ファイル
        speaker_name: 話者名
        segment_length: セグメント長（秒）
    
    Returns:
        成功したらTrue
    """
    print("\n" + "="*70)
    print(f"🎯 新規話者データ準備: {speaker_name}")
    print("="*70)
    
    # 依存関係チェック
    if not check_dependencies():
        print("\n❌ 依存関係エラー。必要なパッケージをインストールしてください。")
        return False
    
    base_dir = Path(__file__).parent
    audio_file = Path(audio_file_path).expanduser()
    
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
        # すでにWAV形式の場合はコピー
        import shutil
        shutil.copy2(audio_file, wav_file)
        print(f"✅ 音声ファイルをコピー: {wav_file}")
    
    # セグメント分割
    segment_count = split_audio_into_segments(
        wav_file,
        segments_dir,
        speaker_name,
        segment_length=segment_length
    )
    
    if segment_count == 0:
        print("❌ セグメント生成失敗")
        return False
    
    # Google Cloud文字起こし
    text_file = lora_dir / "text"
    transcribe_success = transcribe_with_google_cloud(segments_dir, speaker_name, text_file)
    
    if not transcribe_success:
        print("⚠️  文字起こし失敗（手動でtextファイルを作成してください）")
    
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
    print(f"\n1. （オプション）LoRAファインチューニング:")
    print(f"   # Google Cloud VM上でファインチューニング")
    print(f"   # または、ゼロショット音声合成のみで使用可能")
    
    print(f"\n2. 参照音声を準備:")
    print(f"   # 短い参照音声（3-10秒程度）を用意")
    print(f"   # 例: {speaker_name}_reference.wav")
    
    print(f"\n3. 話者を登録:")
    print(f"   cd {base_dir}")
    print(f"   python3 speaker_cli.py add {speaker_name} \\")
    print(f"       {lora_dir}/segments/{speaker_name}_segment_0000.wav \\")
    print(f"       --prompt-text '話者のプロンプトテキスト'")
    
    print(f"\n4. アクティブ化:")
    print(f"   python3 speaker_cli.py set {speaker_name}")
    
    print("\n" + "="*70)
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSL用の新規話者データ準備")
    parser.add_argument("--audio", type=str, required=True, help="音声ファイルパス（例: ~/narisawa_voice.wav）")
    parser.add_argument("--speaker", type=str, required=True, help="話者名（例: narisawa）")
    parser.add_argument("--segment-length", type=float, default=10.0, help="セグメント長（秒）")
    
    args = parser.parse_args()
    
    # Google Cloud Project設定
    if "GOOGLE_CLOUD_PROJECT" not in os.environ:
        os.environ["GOOGLE_CLOUD_PROJECT"] = "president-clone-1762149165"
    
    prepare_speaker_data_wsl(args.audio, args.speaker, args.segment_length)
