"""Local recognition: NVIDIA Parakeet-TDT 0.6B v3 (int8 ONNX) through onnx-asr.

Loaded lazily on first use (about 1.5 s), then kept warm. It detects the language by
itself and covers English, Russian, German and French, so it can stand in for the
cloud engine whenever that is unavailable, and it is the engine used while Lector is
speaking, so echo of its own voice never spends the cloud quota.
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import soxr

from app.asr.base import Transcript, Unavailable

log = logging.getLogger(__name__)


class ParakeetASR:
    name = "local:parakeet-tdt-0.6b-v3"

    def __init__(self, model_dir: Path, threads: int = 4) -> None:
        self.model_dir = model_dir
        self.threads = threads
        self._model: Any = None
        self._lock = threading.Lock()
        self.status = "idle"

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            import onnx_asr
            import onnxruntime as ort

            self.status = "loading"
            started = time.monotonic()
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = self.threads
            opts.inter_op_num_threads = 1
            try:
                self._model = onnx_asr.load_model(
                    "nemo-parakeet-tdt-0.6b-v3",
                    str(self.model_dir),
                    quantization="int8",
                    sess_options=opts,
                )
            except TypeError:
                self._model = onnx_asr.load_model(
                    "nemo-parakeet-tdt-0.6b-v3", str(self.model_dir), quantization="int8"
                )
            except Exception:
                self.status = "error"
                raise
            self.status = "ready"
            log.info("Parakeet loaded in %.1f s", time.monotonic() - started)

    def _recognize(self, wav: bytes) -> tuple[str, float]:
        self.load()
        audio, rate = sf.read(io.BytesIO(wav), dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != 16_000:
            audio = soxr.resample(audio, rate, 16_000)
            rate = 16_000
        duration = len(audio) / rate
        if duration < 0.15:
            return "", duration
        text = self._model.recognize(np.asarray(audio, dtype=np.float32), sample_rate=rate)
        return str(text).strip(), duration

    async def transcribe(self, wav: bytes, language: str | None, prompt: str) -> Transcript:
        started = time.monotonic()
        try:
            text, duration = await asyncio.to_thread(self._recognize, wav)
        except Exception as exc:
            log.exception("local recognition failed")
            raise Unavailable(f"local recognizer failed: {exc}") from exc
        return Transcript(
            text=text,
            engine=self.name,
            language=language,
            duration=duration,
            ms=(time.monotonic() - started) * 1000,
        )
