#!/usr/bin/env python3
"""validate_dataset.py

Quick sanity checks for CosyVoice LoRA dataset folder.
- Verifies segments/*.wav are 24kHz, mono, 16-bit PCM
- Verifies metadata files exist and utt IDs are consistent
- Verifies text file uses TAB delimiter (utt_id\ttext)

Usage:
  python3 validate_dataset.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
import wave


DATA_DIR = Path(__file__).parent
SEGMENTS_DIR = DATA_DIR / "segments"
TEXT_FILE = DATA_DIR / "text"
WAV_SCP = DATA_DIR / "wav.scp"
UTT2SPK = DATA_DIR / "utt2spk"
SPK2UTT = DATA_DIR / "spk2utt"


@dataclass(frozen=True)
class WavInfo:
    path: Path
    channels: int
    sampwidth: int
    framerate: int
    nframes: int


def read_wav_info(path: Path) -> WavInfo:
    with wave.open(str(path), "rb") as wf:
        return WavInfo(
            path=path,
            channels=wf.getnchannels(),
            sampwidth=wf.getsampwidth(),
            framerate=wf.getframerate(),
            nframes=wf.getnframes(),
        )


def read_text_map(path: Path) -> tuple[dict[str, str], int]:
    out: dict[str, str] = {}
    non_tab_lines = 0
    if not path.exists():
        return out, non_tab_lines
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "\t" in line:
            utt_id, text = line.split("\t", 1)
        else:
            non_tab_lines += 1
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"bad text line (expected utt_id + text): {raw!r}")
            utt_id, text = parts
        utt_id = utt_id.strip()
        text = text.strip()
        if not utt_id:
            raise ValueError(f"empty utt_id in text line: {raw!r}")
        out[utt_id] = text
    return out, non_tab_lines


def read_key_value_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"bad line in {path.name}: {raw!r}")
        out[parts[0]] = parts[1]
    return out


def read_spk2utt(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"bad line in {path.name}: {raw!r}")
        out[parts[0]] = parts[1:]
    return out


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not SEGMENTS_DIR.exists():
        errors.append(f"missing segments dir: {SEGMENTS_DIR}")
        print("\n".join(errors))
        return 2

    wavs = sorted(SEGMENTS_DIR.glob("*.wav"))
    if not wavs:
        errors.append(f"no wav files under: {SEGMENTS_DIR}")

    # WAV checks
    bad_wavs = 0
    for wav_path in wavs:
        try:
            info = read_wav_info(wav_path)
        except Exception as e:
            bad_wavs += 1
            errors.append(f"failed to read wav {wav_path.name}: {e}")
            continue

        if info.framerate != 24000:
            bad_wavs += 1
            errors.append(f"{wav_path.name}: sample_rate={info.framerate} (expected 24000)")
        if info.channels != 1:
            bad_wavs += 1
            errors.append(f"{wav_path.name}: channels={info.channels} (expected 1)")
        if info.sampwidth != 2:
            bad_wavs += 1
            errors.append(f"{wav_path.name}: sampwidth={info.sampwidth} bytes (expected 2 = 16-bit)")

    # Metadata existence
    for p in (TEXT_FILE, WAV_SCP, UTT2SPK, SPK2UTT):
        if not p.exists():
            warnings.append(f"missing {p.name} (not fatal for this checker)")

    # ID consistency
    wav_ids = {p.stem for p in wavs}

    if TEXT_FILE.exists():
        try:
            text_map, non_tab_lines = read_text_map(TEXT_FILE)
        except Exception as e:
            errors.append(str(e))
            text_map = {}
            non_tab_lines = 0
        else:
            if non_tab_lines:
                warnings.append(
                    f"text has {non_tab_lines} non-TAB lines; normalize to utt_id<TAB>text before training"
                )
            text_ids = set(text_map.keys())
            missing_text = sorted(wav_ids - text_ids)
            extra_text = sorted(text_ids - wav_ids)
            if missing_text:
                warnings.append(f"text missing for {len(missing_text)} wavs (e.g. {missing_text[0]})")
            if extra_text:
                warnings.append(f"text has {len(extra_text)} extra utts (e.g. {extra_text[0]})")

    if WAV_SCP.exists():
        wav_scp_map = read_key_value_file(WAV_SCP)
        scp_ids = set(wav_scp_map.keys())
        missing_scp = sorted(wav_ids - scp_ids)
        extra_scp = sorted(scp_ids - wav_ids)
        if missing_scp:
            warnings.append(f"wav.scp missing {len(missing_scp)} utts (e.g. {missing_scp[0]})")
        if extra_scp:
            warnings.append(f"wav.scp has {len(extra_scp)} extra utts (e.g. {extra_scp[0]})")

        # Basic path sanity: looks like an absolute unix path
        bad_paths = 0
        for utt_id, path_str in list(wav_scp_map.items())[:50]:
            if not path_str.startswith("/"):
                bad_paths += 1
        if bad_paths:
            warnings.append("wav.scp paths may not be absolute unix paths (check WSL/Vm path mapping)")

    if UTT2SPK.exists():
        utt2spk_map = read_key_value_file(UTT2SPK)
        utt2spk_ids = set(utt2spk_map.keys())
        if utt2spk_ids and utt2spk_ids != wav_ids:
            warnings.append(
                f"utt2spk utt count={len(utt2spk_ids)} differs from wav count={len(wav_ids)}"
            )

    if SPK2UTT.exists():
        spk2utt_map = read_spk2utt(SPK2UTT)
        if len(spk2utt_map) != 1:
            warnings.append(f"spk2utt has {len(spk2utt_map)} speakers (expected 1 for single-speaker finetune)")

    # Summary
    print(f"WAV files: {len(wavs)}")
    if errors:
        print("\nErrors:")
        for e in errors[:50]:
            print(f"- {e}")
        if len(errors) > 50:
            print(f"- ... and {len(errors) - 50} more")

    if warnings:
        print("\nWarnings:")
        for w in warnings[:50]:
            print(f"- {w}")
        if len(warnings) > 50:
            print(f"- ... and {len(warnings) - 50} more")

    if errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
