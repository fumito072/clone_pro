import asyncio
import json
import os
import time

import websockets

from cosyvoice_engine import CosyVoiceEngine


tts_engine: CosyVoiceEngine | None = None
_engine_lock: asyncio.Lock | None = None
_infer_semaphore: asyncio.Semaphore | None = None


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


async def _get_engine() -> CosyVoiceEngine:
    global tts_engine, _engine_lock
    if tts_engine is not None:
        return tts_engine
    if _engine_lock is None:
        _engine_lock = asyncio.Lock()

    async with _engine_lock:
        if tts_engine is not None:
            return tts_engine
        print(f"[{_ts()}] [TTS] Initializing CosyVoiceEngine...", flush=True)
        tts_engine = await asyncio.to_thread(CosyVoiceEngine)
        print(f"[{_ts()}] [TTS] CosyVoiceEngine ready", flush=True)
        return tts_engine


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _get_infer_semaphore() -> asyncio.Semaphore:
    global _infer_semaphore
    if _infer_semaphore is None:
        max_concurrency = int(os.getenv("TTS_MAX_CONCURRENCY", "1"))
        _infer_semaphore = asyncio.Semaphore(max(1, max_concurrency))
    return _infer_semaphore


async def websocket_handler(ws):
    path = getattr(ws, "path", "/")
    if path not in {"/tts", "/"}:
        await ws.send(json.dumps({"status": "error", "message": f"Invalid path: {path}"}))
        return

    await ws.send(
        json.dumps(
            {
                "status": "connected",
                "message": "TTS Server Ready (CosyVoice LoRA)",
            }
        )
    )

    async for message in ws:
        try:
            req = json.loads(message)
        except Exception:
            await ws.send(json.dumps({"status": "error", "message": "Invalid JSON"}))
            continue

        text = (req.get("text") or "").strip()
        if not text:
            await ws.send(json.dumps({"status": "error", "message": "Missing 'text'"}))
            continue

        speaker = req.get("speaker") or (tts_engine.get_default_speaker() if tts_engine else None)  # type: ignore[union-attr]
        speaker = speaker or os.getenv("SPEAKER_ID", "default")

        stream = bool(req.get("stream", _truthy(os.getenv("TTS_STREAM"))))
        speed = float(req.get("speed", os.getenv("TTS_SPEED", "1.0")))

        try:
            engine = await _get_engine()

            # Avoid overlapping GPU inference which can trigger CUDA OOM.
            sem = _get_infer_semaphore()
            async with sem:

                if stream:
                    await ws.send(
                        json.dumps(
                            {
                                "status": "start",
                                "stream": True,
                                "format": "pcm_s16le",
                                "channels": 1,
                                "sample_rate": 24000,
                            }
                        )
                    )

                    # NOTE: stream=True is best-effort. Heavy inference can block; for stability we
                    # generate chunks in a thread and then send them.
                    chunks: list[bytes] = await asyncio.to_thread(
                        lambda: list(engine.stream_sft_pcm(text, speaker, speed=speed))
                    )
                    for pcm_chunk in chunks:
                        await ws.send(pcm_chunk)

                    await ws.send(json.dumps({"status": "done"}))

                else:
                    pcm = await asyncio.to_thread(engine.synthesize_sft_pcm, text, speaker, speed)
                    await ws.send(
                        json.dumps(
                            {
                                "status": "complete",
                                "format": "pcm_s16le",
                                "channels": 1,
                                "sample_rate": 24000,
                                "size": len(pcm),
                            }
                        )
                    )
                    await ws.send(pcm)
                    await ws.send(json.dumps({"status": "done"}))

        except Exception as exc:
            await ws.send(json.dumps({"status": "error", "message": str(exc)}))


async def main():
    global tts_engine
    # Lazy-init engine to start listening immediately (engine init can take tens of seconds)
    tts_engine = None

    host = os.getenv("TTS_HOST", "0.0.0.0")
    port = int(os.getenv("TTS_PORT", "8002"))

    print(f"[{_ts()}] [TTS] server listening on {host}:{port}", flush=True)
    async with websockets.serve(
        websocket_handler,
        host,
        port,
        ping_interval=None,
        max_size=None,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
