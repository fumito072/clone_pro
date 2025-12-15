#!/usr/bin/env python3
"""
transcribe_segments.py
Google Cloud Speech-to-Text APIを使って新規セグメントの文字起こしを自動生成

使い方:
    # 認証設定
    gcloud auth application-default login
    
    # 実行
    python3 transcribe_segments.py
"""

import os
from pathlib import Path
from google.cloud import speech

# 設定
SPEAKER = "narisawa"
DATA_DIR = Path(__file__).parent
SEGMENTS_DIR = DATA_DIR / "segments"
TEXT_FILE = DATA_DIR / "text"

# Google Cloud認証確認
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not Path.home().joinpath(".config/gcloud/application_default_credentials.json").exists():
    print("⚠️  Google Cloud認証が必要です")
    print("   以下のコマンドを実行してください:")
    print("   gcloud auth application-default login")
    print()
    exit(1)

print("=" * 60)
print("🎤 Google Speech-to-Text 文字起こし")
print("=" * 60)
print()

# 既存のtextファイルから文字起こし済みの発話IDを取得
existing_utts = set()
existing_lines = []
if TEXT_FILE.exists():
    with open(TEXT_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                existing_lines.append(line)
                utt_id = line.split()[0] if line else None
                if utt_id:
                    existing_utts.add(utt_id)
    print(f"📝 既存の文字起こし: {len(existing_utts)}個")
else:
    print(f"📝 既存の文字起こし: なし（新規作成）")

# 全WAVファイルを取得
wav_files = sorted(SEGMENTS_DIR.glob(f"{SPEAKER}_segment_*.wav"))
print(f"📂 音声ファイル: {len(wav_files)}個")

# 文字起こしが必要なファイルを抽出
new_files = [f for f in wav_files if f.stem not in existing_utts]
print(f"🆕 文字起こしが必要: {len(new_files)}個")
print()

if not new_files:
    print("✅ 全てのセグメントに文字起こしがあります")
    exit(0)

# Google Speech-to-Text クライアント初期化
print("🔄 Google Speech-to-Text API接続中...")
client = speech.SpeechClient()
print("✅ API接続完了")
print()

# 文字起こし実行
print("🎤 文字起こし実行中...")
print()

transcriptions = []
for i, wav_file in enumerate(new_files, 1):
    print(f"[{i}/{len(new_files)}] {wav_file.name}...", end=" ", flush=True)
    
    try:
        # 音声ファイル読み込み
        with open(wav_file, "rb") as audio_file:
            content = audio_file.read()
        
        # Speech-to-Text API設定
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=24000,
            language_code="ja-JP",
            enable_automatic_punctuation=True,  # 句読点を自動追加
            model="latest_long",  # 最新の長文モデル
        )
        
        # 文字起こし実行
        response = client.recognize(config=config, audio=audio)
        
        # 結果取得
        if response.results:
            text = ""
            for result in response.results:
                text += result.alternatives[0].transcript
            
            text = text.strip()
            utt_id = wav_file.stem
            transcriptions.append((utt_id, text))
            
            # 簡略表示
            display_text = text[:40] + "..." if len(text) > 40 else text
            print(f"✅ {display_text}")
        else:
            print(f"⚠️  認識結果なし（無音または短すぎる可能性）")
        
    except Exception as e:
        print(f"❌ エラー: {e}")

print()

# textファイルに書き込み
if transcriptions or existing_lines:
    print("💾 textファイルを更新中...")
    
    # 全ての発話IDと文字起こしを辞書に格納
    all_transcriptions = {}
    
    # 既存の内容を読み込み
    for line in existing_lines:
        parts = line.split(None, 1)  # 最初の空白で分割
        if len(parts) == 2:
            utt_id, text = parts
            all_transcriptions[utt_id] = text
    
    # 新規の文字起こしを追加
    for utt_id, text in transcriptions:
        all_transcriptions[utt_id] = text
    
    # 発話IDでソートして書き込み
    with open(TEXT_FILE, "w") as f:
        for utt_id in sorted(all_transcriptions.keys()):
            text = all_transcriptions[utt_id]
            f.write(f"{utt_id} {text}\n")
    
    print(f"✅ {len(transcriptions)}件の文字起こしを追加")
    print(f"📄 合計: {len(all_transcriptions)}件")
    print()
    
    # サンプル表示
    if transcriptions:
        print("📄 追加した文字起こし（サンプル）:")
        for utt_id, text in transcriptions[:5]:
            display_text = text[:60] + "..." if len(text) > 60 else text
            print(f"   {utt_id}: {display_text}")
        if len(transcriptions) > 5:
            print(f"   ... 他 {len(transcriptions) - 5}件")

print()
print("=" * 60)
print("✅ 文字起こし完了！")
print("=" * 60)
print()
print("📊 統計:")
print(f"   - 既存の文字起こし: {len(existing_utts)}個")
print(f"   - 新規の文字起こし: {len(transcriptions)}個")
print(f"   - 合計: {len(existing_utts) + len(transcriptions)}個")
print()
print("🎯 次のステップ:")
print("   1. textファイルの内容を確認・修正（必要に応じて）")
print("   2. メタデータを更新:")
print("      python3 update_metadata.py")
print("   3. WSL側に転送:")
print("      bash transfer_to_wsl_http.sh")
print()
