"""
話者管理CLI - 既存のディレクトリ構造を維持したまま話者を管理

使用例:
    # 話者一覧
    python speaker_cli.py list
    
    # 新しい話者を追加
    python speaker_cli.py add tanaka ~/voices/tanaka.wav "田中太郎です"
    
    # アクティブな話者を切り替え
    python speaker_cli.py set tanaka
    
    # 現在の話者を表示
    python speaker_cli.py current
"""

import argparse
from pathlib import Path
from speaker_manager import SpeakerManager

def cmd_list(manager: SpeakerManager, args):
    """話者一覧を表示"""
    speakers = manager.list_speakers()
    
    if not speakers:
        print("📭 登録されている話者はいません")
        return
    
    print("="*70)
    print(f"🎙️  登録されている話者: {len(speakers)}人")
    print("="*70)
    
    for name, info in speakers.items():
        status = "✅ アクティブ" if info.get("active") else "  "
        print(f"\n{status} 👤 {name}")
        print(f"   📂 参照音声: CosyVoice/asset/{info['reference_audio']}")
        
        if info.get('long_audio'):
            print(f"   📂 ファインチューニング用: CosyVoice/asset/{info['long_audio']}")
        
        if info.get('prompt_text'):
            preview = info['prompt_text'][:50] + "..." if len(info['prompt_text']) > 50 else info['prompt_text']
            print(f"   💬 プロンプト: {preview}")
        
        if info.get('lora_model'):
            lora_dir = Path(__file__).parent / info['lora_model']
            if lora_dir.exists():
                checkpoints = list(lora_dir.glob("*.pth")) if lora_dir.is_dir() else []
                print(f"   🔧 LoRAモデル: {info['lora_model']}/ ({len(checkpoints)} checkpoint)")
            else:
                print(f"   🔧 LoRAモデル: {info['lora_model']}/ (未作成)")
    
    print("="*70)

def cmd_add(manager: SpeakerManager, args):
    """新しい話者を追加"""
    reference_path = Path(args.reference_audio)
    
    if not reference_path.exists():
        print(f"❌ 音声ファイルが見つかりません: {reference_path}")
        return
    
    long_audio_path = None
    if args.long_audio:
        long_audio_path = Path(args.long_audio)
        if not long_audio_path.exists():
            print(f"⚠️ ファインチューニング用音声が見つかりません: {long_audio_path}")
            long_audio_path = None
    
    success = manager.add_speaker(
        speaker_name=args.speaker_name,
        reference_audio_path=reference_path,
        long_audio_path=long_audio_path,
        prompt_text=args.prompt_text or f"{args.speaker_name}の音声です"
    )
    
    if success:
        print(f"\n✅ 話者 '{args.speaker_name}' を追加しました")
        print(f"\n📂 ファイルの配置場所:")
        print(f"   CosyVoice/asset/{args.speaker_name}_reference_24k.wav")
        if long_audio_path:
            print(f"   CosyVoice/asset/{args.speaker_name}_voice_long.wav")
        
        print(f"\n💡 次のステップ:")
        print(f"   # アクティブな話者に設定")
        print(f"   python speaker_cli.py set {args.speaker_name}")
        
        if long_audio_path:
            print(f"\n   # ファインチューニングを実行 (オプション)")
            print(f"   python finetune_lora.py --speaker {args.speaker_name}")

def cmd_set(manager: SpeakerManager, args):
    """アクティブな話者を設定"""
    success = manager.set_active_speaker(args.speaker_name)
    
    if success:
        paths = manager.get_speaker_paths(args.speaker_name)
        print(f"\n📋 使用される設定:")
        print(f"   参照音声: {paths['reference_audio']}")
        print(f"   プロンプト: {paths['prompt_text'][:50]}...")
        
        print(f"\n✅ controller.pyで '{args.speaker_name}' の声が使用されます")

def cmd_current(manager: SpeakerManager, args):
    """現在のアクティブな話者を表示"""
    active = manager.get_active_speaker()
    
    if not active:
        print("⚠️ アクティブな話者が設定されていません")
        return
    
    print("="*70)
    print(f"🎯 現在のアクティブな話者: {active['name']}")
    print("="*70)
    print(f"\n📂 参照音声: CosyVoice/asset/{active['reference_audio']}")
    
    if active.get('long_audio'):
        print(f"📂 ファインチューニング用: CosyVoice/asset/{active['long_audio']}")
    
    if active.get('prompt_text'):
        print(f"\n💬 プロンプトテキスト:")
        print(f"   {active['prompt_text']}")
    
    print("="*70)

def main():
    parser = argparse.ArgumentParser(description='話者管理CLI')
    subparsers = parser.add_subparsers(dest='command', help='コマンド')
    
    # list コマンド
    parser_list = subparsers.add_parser('list', help='話者一覧を表示')
    
    # add コマンド
    parser_add = subparsers.add_parser('add', help='新しい話者を追加')
    parser_add.add_argument('speaker_name', help='話者名（例: tanaka）')
    parser_add.add_argument('reference_audio', help='参照音声ファイルのパス')
    parser_add.add_argument('--long-audio', help='ファインチューニング用の長い音声ファイル')
    parser_add.add_argument('--prompt-text', help='プロンプトテキスト')
    
    # set コマンド
    parser_set = subparsers.add_parser('set', help='アクティブな話者を設定')
    parser_set.add_argument('speaker_name', help='話者名')
    
    # current コマンド
    parser_current = subparsers.add_parser('current', help='現在のアクティブな話者を表示')
    
    args = parser.parse_args()
    
    # SpeakerManagerの初期化
    manager = SpeakerManager()
    
    # コマンド実行
    if args.command == 'list':
        cmd_list(manager, args)
    elif args.command == 'add':
        cmd_add(manager, args)
    elif args.command == 'set':
        cmd_set(manager, args)
    elif args.command == 'current':
        cmd_current(manager, args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
