import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import torch


def _fade_out(audio: torch.Tensor, sample_rate: int = 24000, fade_ms: int = 10) -> torch.Tensor:
    if fade_ms <= 0:
        return audio
    if audio.numel() == 0:
        return audio
    fade_samples = int(sample_rate * (fade_ms / 1000.0))
    if fade_samples <= 0:
        return audio
    total = audio.shape[-1]
    fade_samples = min(fade_samples, total)
    if fade_samples <= 1:
        return audio
    ramp = torch.linspace(1.0, 0.0, steps=fade_samples, device=audio.device, dtype=audio.dtype)
    audio = audio.clone()
    audio[..., -fade_samples:] = audio[..., -fade_samples:] * ramp
    return audio


def _float_audio_to_int16_bytes(audio_np):
    # Clip to prevent int16 wrap-around which can cause sharp clicks.
    import numpy as np

    audio_np = np.asarray(audio_np, dtype=np.float32)
    audio_np = np.clip(audio_np, -1.0, 1.0)
    audio_i32 = np.rint(audio_np * 32767.0).astype(np.int32)
    audio_i32 = np.clip(audio_i32, -32768, 32767)
    return audio_i32.astype(np.int16).tobytes()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_state_dict(checkpoint: Any) -> dict[str, torch.Tensor]:
    """Best-effort extraction of a plain state_dict from various checkpoint formats."""
    if isinstance(checkpoint, dict):
        model_dict = checkpoint.get("model")
        if isinstance(model_dict, dict):
            return {k: v for k, v in model_dict.items() if isinstance(v, torch.Tensor)}

        state_dict = checkpoint.get("state_dict")
        if isinstance(state_dict, dict):
            return {k: v for k, v in state_dict.items() if isinstance(v, torch.Tensor)}

        # Fall back: filter out common metadata keys and non-tensors
        skip_keys = {"epoch", "step", "optimizer", "scheduler", "scaler", "args", "cfg"}
        return {
            k: v
            for k, v in checkpoint.items()
            if k not in skip_keys and isinstance(v, torch.Tensor)
        }

    raise TypeError(f"Unsupported checkpoint type: {type(checkpoint).__name__}")


def _resolve_speaker_id(spk2embedding: Any, preferred_id: str) -> str:
    if isinstance(spk2embedding, dict) and preferred_id in spk2embedding:
        return preferred_id
    if isinstance(spk2embedding, dict) and spk2embedding:
        return next(iter(spk2embedding.keys()))
    return preferred_id


def _to_embedding_tensor(value: Any) -> torch.Tensor:
    if isinstance(value, list):
        tensor = torch.tensor(value)
    elif isinstance(value, torch.Tensor):
        tensor = value
    else:
        tensor = torch.tensor(value)

    if tensor.dim() == 1:
        tensor = tensor.unsqueeze(0)
    return tensor


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _autocast_context():
    if not torch.cuda.is_available():
        return nullcontext()
    # Default: on. Can disable with TTS_FP16=0
    if _truthy(os.getenv("TTS_FP16", "1")):
        return torch.autocast(device_type="cuda", dtype=torch.float16)
    return nullcontext()


class CosyVoiceEngine:
    def __init__(self, model_dir: str | Path | None = None, speaker_config_path: str | Path | None = None):
        cosyvoice_repo_dir_env = os.getenv("COSYVOICE_REPO_DIR")
        cosyvoice_repo_dir = Path(cosyvoice_repo_dir_env) if cosyvoice_repo_dir_env else (Path.home() / "CosyVoice")
        if cosyvoice_repo_dir.exists() and str(cosyvoice_repo_dir) not in sys.path:
            sys.path.insert(0, str(cosyvoice_repo_dir))

        requested_model_dir = Path(
            model_dir
            or os.getenv("COSYVOICE_MODEL_DIR", "")
            or str(cosyvoice_repo_dir / "pretrained_models" / "CosyVoice2-0.5B" / "CosyVoice-BlankEN")
        )

        # CosyVoice expects cosyvoice2.yaml to exist under model_dir. If not, fall back.
        candidate_dirs: list[Path] = [requested_model_dir]
        candidate_dirs.append(cosyvoice_repo_dir / "pretrained_models" / "CosyVoice2-0.5B")
        if requested_model_dir.name == "CosyVoice-BlankEN":
            candidate_dirs.append(requested_model_dir.parent)

        resolved_model_dir = None
        for cand in candidate_dirs:
            if (cand / "cosyvoice2.yaml").is_file() or (cand / "cosyvoice.yaml").is_file():
                resolved_model_dir = cand
                break

        self.model_dir = resolved_model_dir or requested_model_dir
        self.speaker_config_path = Path(
            speaker_config_path
            or os.getenv("SPEAKER_CONFIG_PATH", "")
            or str(Path(__file__).resolve().parent / "speaker_config.json")
        )

        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2 as _CosyVoice
        except Exception:
            from cosyvoice.cli.cosyvoice import CosyVoice as _CosyVoice  # type: ignore

        self.model = _CosyVoice(str(self.model_dir))

        self._speaker_config: dict[str, Any] = {"speakers": {}, "default_speaker": None}
        if self.speaker_config_path.exists():
            self._speaker_config = _load_json(self.speaker_config_path)

        self._lora_cache_llm: dict[str, dict[str, torch.Tensor]] = {}
        self._lora_cache_flow: dict[str, dict[str, torch.Tensor]] = {}
        self._embedding_cache: dict[str, torch.Tensor] = {}

    def get_default_speaker(self) -> str | None:
        default = self._speaker_config.get("default_speaker")
        if isinstance(default, str) and default:
            return default
        speakers = self._speaker_config.get("speakers")
        if isinstance(speakers, dict) and speakers:
            return next(iter(speakers.keys()))
        return None

    def _apply_state_dict(self, module: Any, state: dict[str, torch.Tensor]) -> None:
        if module is None:
            raise RuntimeError("Target module not found (cannot apply LoRA checkpoint)")
        module.load_state_dict(state, strict=False)

    def load_speaker_lora(self, speaker_id: str) -> bool:
        speakers = self._speaker_config.get("speakers")
        if not isinstance(speakers, dict) or speaker_id not in speakers:
            raise KeyError(f"Speaker '{speaker_id}' not found in {self.speaker_config_path}")

        info = speakers[speaker_id]
        if not isinstance(info, dict):
            raise TypeError(f"Invalid speaker config for '{speaker_id}'")

        llm_path = info.get("llm_lora_model_path") or info.get("lora_model_path")
        flow_path = info.get("flow_lora_model_path")
        embedding_path = info.get("spk_embedding_path")

        # 1) Load/apply LLM LoRA (whole-pt)
        if llm_path:
            if speaker_id not in self._lora_cache_llm:
                ckpt = torch.load(str(llm_path), map_location="cpu")
                self._lora_cache_llm[speaker_id] = _extract_state_dict(ckpt)

            llm_module = getattr(getattr(self.model, "model", None), "llm", None)
            self._apply_state_dict(llm_module, self._lora_cache_llm[speaker_id])

        # 2) Load/apply Flow LoRA (optional)
        if flow_path:
            if speaker_id not in self._lora_cache_flow:
                ckpt = torch.load(str(flow_path), map_location="cpu")
                self._lora_cache_flow[speaker_id] = _extract_state_dict(ckpt)

            flow_module = getattr(getattr(self.model, "model", None), "flow", None)
            if flow_module is None:
                flow_module = getattr(getattr(self.model, "model", None), "flow_model", None)
            self._apply_state_dict(flow_module, self._lora_cache_flow[speaker_id])

        # 3) Load/register speaker embedding
        if embedding_path and speaker_id not in self._embedding_cache:
            spk2embedding = torch.load(str(embedding_path), map_location="cpu")
            resolved_id = _resolve_speaker_id(spk2embedding, speaker_id)
            embedding = _to_embedding_tensor(spk2embedding[resolved_id])
            self._embedding_cache[speaker_id] = embedding

        if speaker_id in self._embedding_cache:
            # CosyVoice2 uses frontend.spk2info for speaker registry
            self.model.frontend.spk2info[speaker_id] = {"embedding": self._embedding_cache[speaker_id]}

        return True

    def synthesize_sft_audio(self, text: str, speaker: str, speed: float = 1.0) -> torch.Tensor:
        self.load_speaker_lora(speaker)
        with torch.inference_mode(), _autocast_context():
            result = list(self.model.inference_sft(text, speaker, stream=False, speed=speed))
            audio = torch.cat(
                [chunk["tts_speech"] for chunk in result if "tts_speech" in chunk], dim=1
            )
            fade_ms = int(os.getenv("TTS_FADE_OUT_MS", "10"))
            audio = _fade_out(audio, sample_rate=24000, fade_ms=fade_ms)
            return audio

    def stream_sft_pcm(self, text: str, speaker: str, speed: float = 1.0):
        self.load_speaker_lora(speaker)
        with torch.inference_mode(), _autocast_context():
            for chunk in self.model.inference_sft(text, speaker, stream=True, speed=speed):
                if "tts_speech" not in chunk:
                    continue
                audio_np = chunk["tts_speech"].squeeze(0).detach().cpu().numpy()
                yield _float_audio_to_int16_bytes(audio_np)

    def synthesize_sft_pcm(self, text: str, speaker: str, speed: float = 1.0) -> bytes:
        audio = self.synthesize_sft_audio(text, speaker, speed=speed)
        audio_np = audio.squeeze(0).detach().cpu().numpy()
        return _float_audio_to_int16_bytes(audio_np)
