"""
話者管理システム - 既存のディレクトリ構造を維持

既存の構造:
  mouth_tts/CosyVoice/asset/
    ├── reference_voice_24k.wav  (yotaro用の参照音声)
    └── yotaro_voice_long.wav    (yotaro用のファインチューニング音声)

新しい話者を追加する場合も同じ場所に配置:
  mouth_tts/CosyVoice/asset/
    ├── reference_voice_24k.wav      (yotaro - 既存)
    ├── yotaro_voice_long.wav        (yotaro - 既存)
    ├── tanaka_reference_24k.wav     (tanaka用参照音声)
    ├── tanaka_voice_long.wav        (tanakaファインチューニング用)
    └── suzuki_reference_24k.wav     (suzuki用参照音声)

LoRAモデルも既存の構造を維持:
  mouth_tts/
    ├── lora_yotaro/    (yotaro用LoRAモデル)
    ├── lora_tanaka/    (tanaka用LoRAモデル)
    └── lora_suzuki/    (suzuki用LoRAモデル)
"""

import json
from pathlib import Path
from typing import Dict, Optional
import shutil

class SpeakerManager:
    """話者管理クラス - 既存の構造を維持"""
    
    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            self.base_dir = Path(__file__).parent
        else:
            self.base_dir = Path(base_dir)
        
        self.asset_dir = self.base_dir / "CosyVoice" / "asset"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        
        # 話者情報を管理するJSONファイル
        self.speakers_config_path = self.base_dir / "speakers_config.json"
        self.speakers = self._load_speakers_config()
    
    def _load_speakers_config(self) -> Dict:
        """話者設定を読み込み"""
        if self.speakers_config_path.exists():
            with open(self.speakers_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # デフォルト設定（既存のyotaro）
            default_config = {
                "yotaro": {
                    "reference_audio": "reference_voice_24k.wav",
                    "long_audio": "yotaro_voice_long.wav",
                    "prompt_text": "はじめまして成沢木怜です。私はものづくりやプログラミングアプリケーション開発に興味があります。特にアプリケーション開発は素早くデモを作ることが得意です。一方でものづくりも得意でしてデバイスの設計やCADデータを用いた3Dプリンターのデータの作成、さらにそれらに動きを合わせて動きの制御を行う仕組みを作ることも得意です。これらを組み合わせることでさまざまな新しいものを作っていくことに挑戦しています。",
                    "lora_model": "lora_yotaro",
                    "active": True
                }
            }
            self._save_speakers_config(default_config)
            return default_config
    
    def _save_speakers_config(self, config: Dict):
        """話者設定を保存"""
        with open(self.speakers_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    def add_speaker(self, 
                   speaker_name: str,
                   reference_audio_path: Path,
                   long_audio_path: Optional[Path] = None,
                   prompt_text: str = "") -> bool:
        """
        新しい話者を追加
        
        Args:
            speaker_name: 話者名（例: "tanaka"）
            reference_audio_path: 参照音声ファイルのパス
            long_audio_path: ファインチューニング用の長い音声（オプション）
            prompt_text: プロンプトテキスト
        
        Returns:
            成功したらTrue
        """
        print(f"\n👤 話者追加: {speaker_name}")
        
        # 参照音声をコピー
        reference_filename = f"{speaker_name}_reference_24k.wav"
        reference_dest = self.asset_dir / reference_filename
        
        try:
            shutil.copy2(reference_audio_path, reference_dest)
            print(f"✅ 参照音声をコピー: {reference_dest}")
        except Exception as e:
            print(f"❌ 参照音声のコピー失敗: {e}")
            return False
        
        # 長い音声（ファインチューニング用）をコピー
        long_filename = None
        if long_audio_path and long_audio_path.exists():
            long_filename = f"{speaker_name}_voice_long.wav"
            long_dest = self.asset_dir / long_filename
            try:
                shutil.copy2(long_audio_path, long_dest)
                print(f"✅ ファインチューニング用音声をコピー: {long_dest}")
            except Exception as e:
                print(f"⚠️ ファインチューニング用音声のコピー失敗: {e}")
        
        # 話者情報を追加
        self.speakers[speaker_name] = {
            "reference_audio": reference_filename,
            "long_audio": long_filename if long_filename else None,
            "prompt_text": prompt_text,
            "lora_model": f"lora_{speaker_name}",
            "active": False  # デフォルトは非アクティブ
        }
        
        self._save_speakers_config(self.speakers)
        print(f"✅ 話者 '{speaker_name}' を追加しました")
        return True
    
    def set_active_speaker(self, speaker_name: str) -> bool:
        """アクティブな話者を設定"""
        if speaker_name not in self.speakers:
            print(f"❌ 話者 '{speaker_name}' が見つかりません")
            return False
        
        # 全ての話者を非アクティブに
        for name in self.speakers:
            self.speakers[name]["active"] = False
        
        # 指定した話者をアクティブに
        self.speakers[speaker_name]["active"] = True
        self._save_speakers_config(self.speakers)
        
        print(f"✅ アクティブな話者を '{speaker_name}' に設定しました")
        return True
    
    def get_active_speaker(self) -> Optional[Dict]:
        """現在アクティブな話者の情報を取得"""
        for name, info in self.speakers.items():
            if info.get("active", False):
                return {"name": name, **info}
        
        # アクティブな話者がいない場合は最初の話者を返す
        if self.speakers:
            first_speaker = list(self.speakers.keys())[0]
            return {"name": first_speaker, **self.speakers[first_speaker]}
        
        return None
    
    def list_speakers(self) -> Dict:
        """全話者のリストを取得"""
        return self.speakers
    
    def get_speaker_paths(self, speaker_name: str = None) -> Dict[str, Path]:
        """話者の音声ファイルパスを取得"""
        if speaker_name is None:
            active = self.get_active_speaker()
            if not active:
                raise ValueError("アクティブな話者が設定されていません")
            speaker_name = active["name"]
        
        if speaker_name not in self.speakers:
            raise ValueError(f"話者 '{speaker_name}' が見つかりません")
        
        info = self.speakers[speaker_name]
        
        paths = {
            "reference_audio": self.asset_dir / info["reference_audio"],
            "prompt_text": info["prompt_text"],
            "lora_model": self.base_dir / info["lora_model"] if info.get("lora_model") else None
        }
        
        if info.get("long_audio"):
            paths["long_audio"] = self.asset_dir / info["long_audio"]
        
        return paths

def main():
    """使用例"""
    manager = SpeakerManager()
    
    print("="*70)
    print("🎙️  話者管理システム")
    print("="*70)
    
    # 現在の話者一覧
    print("\n📋 登録されている話者:")
    speakers = manager.list_speakers()
    for name, info in speakers.items():
        status = "✅ アクティブ" if info.get("active") else "  "
        print(f"  {status} {name}")
        print(f"      参照音声: {info['reference_audio']}")
        if info.get('long_audio'):
            print(f"      ファインチューニング用: {info['long_audio']}")
    
    # アクティブな話者
    active = manager.get_active_speaker()
    if active:
        print(f"\n🎯 アクティブな話者: {active['name']}")
        paths = manager.get_speaker_paths()
        print(f"   参照音声: {paths['reference_audio']}")
    
    print("\n" + "="*70)
    print("💡 使用方法:")
    print("="*70)
    print("\n# 新しい話者を追加")
    print("from speaker_manager import SpeakerManager")
    print("manager = SpeakerManager()")
    print('manager.add_speaker(')
    print('    speaker_name="tanaka",')
    print('    reference_audio_path=Path("path/to/tanaka_voice.wav"),')
    print('    prompt_text="田中太郎です。よろしくお願いします。"')
    print(')')
    print("\n# アクティブな話者を切り替え")
    print('manager.set_active_speaker("tanaka")')
    print("="*70)

if __name__ == "__main__":
    main()
