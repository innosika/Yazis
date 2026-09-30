"""Speech synthesis engines and the single inference worker in front of them.

There is exactly one model in memory and one thread running it: parallel inference on
a laptop CPU only makes every request slower. Requests queue by priority (what the
listener needs *now*, then prefetch, then background work such as the browser
extension); identical requests share one computation; a queued request whose client
went away is dropped before it costs anything.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from app.tts import dsp
from app.tts.align import Chunk, TimedSpan, Token, align
from app.tts.voices import VOICES_BY_ID, get_voice

log = logging.getLogger(__name__)

PRIORITY = {"now": 0, "prefetch": 1, "background": 2}


@dataclass(frozen=True, slots=True)
class VoiceMix:
    """One voice, or two voices blended: ``mix`` is the weight of ``blend``."""

    id: str
    blend: str | None = None
    mix: float = 0.5

    def key(self) -> str:
        if not self.blend or self.mix <= 0:
            return self.id
        return f"{self.id}+{self.blend}@{self.mix:.2f}"


@dataclass(slots=True)
class Synthesis:
    audio: np.ndarray
    words: list[TimedSpan]
    duration: float
    compute_ms: float


class Engine(Protocol):
    name: str

    def load(self) -> None: ...

    def synthesize(
        self, spoken: str, voice: VoiceMix, speed: float
    ) -> tuple[np.ndarray, list[Chunk]]: ...

    def health(self) -> dict[str, Any]: ...


class KokoroEngine:
    name = "kokoro-82m-v1.0"

    def __init__(self, repo_id: str, threads: int) -> None:
        self.repo_id = repo_id
        self.threads = threads
        self._pipelines: dict[str, Any] = {}
        self._voices: dict[str, Any] = {}
        self._espeak = False

    def load(self) -> None:
        import torch
        from kokoro import KModel, KPipeline

        torch.set_num_threads(self.threads)
        started = time.monotonic()
        model = KModel(repo_id=self.repo_id).eval()
        for lang in ("a", "b"):
            self._pipelines[lang] = KPipeline(lang_code=lang, repo_id=self.repo_id, model=model)
        fallback = getattr(self._pipelines["a"].g2p, "fallback", None)
        self._espeak = fallback is not None
        if not self._espeak:
            log.warning("espeak fallback unavailable: unknown words would be skipped")
        log.info("Kokoro loaded in %.1f s (%d threads)", time.monotonic() - started, self.threads)

    def _voice_tensor(self, voice: VoiceMix) -> Any:
        key = voice.key()
        if key in self._voices:
            return self._voices[key]
        pipe = self._pipelines[get_voice(voice.id).lang_code]
        base = pipe.load_voice(voice.id)
        if voice.blend and voice.mix > 0:
            other = pipe.load_voice(voice.blend)
            w = max(0.0, min(1.0, voice.mix))
            tensor = base * (1.0 - w) + other * w
        else:
            tensor = base
        self._voices[key] = tensor
        return tensor

    def synthesize(
        self, spoken: str, voice: VoiceMix, speed: float
    ) -> tuple[np.ndarray, list[Chunk]]:
        import torch

        pipe = self._pipelines[get_voice(voice.id).lang_code]
        pack = self._voice_tensor(voice)
        parts: list[np.ndarray] = []
        chunks: list[Chunk] = []
        with torch.inference_mode():
            for r in pipe(spoken, voice=pack, speed=speed, split_pattern=None):
                if r.audio is None:
                    continue
                audio = r.audio.detach().cpu().numpy().astype(np.float32)
                tokens = [
                    Token(t.text, t.whitespace, t.start_ts, t.end_ts) for t in (r.tokens or [])
                ]
                parts.append(audio)
                chunks.append(Chunk(r.graphemes, tokens, len(audio) / dsp.SAMPLE_RATE))
        audio = np.concatenate(parts) if parts else dsp.silence(0.2)
        return audio, chunks

    def health(self) -> dict[str, Any]:
        return {"engine": self.name, "espeak_fallback": self._espeak, "voices": len(VOICES_BY_ID)}


class FakeEngine:
    """Deterministic stand-in for tests: 0.25 s per word of quiet tone."""

    name = "fake"

    def load(self) -> None:
        return None

    def synthesize(
        self, spoken: str, voice: VoiceMix, speed: float
    ) -> tuple[np.ndarray, list[Chunk]]:
        get_voice(voice.id)
        tokens: list[Token] = []
        t = 0.0
        for m in re.finditer(r"(\w[\w'-]*|[^\w\s])(\s*)", spoken):
            word, ws = m.group(1), m.group(2)
            dur = 0.25 / speed if word[0].isalnum() else 0.0
            tokens.append(Token(word, ws, t if dur else None, t + dur if dur else None))
            t += dur
        n = int(t * dsp.SAMPLE_RATE) or int(0.2 * dsp.SAMPLE_RATE)
        audio = (0.1 * np.sin(np.arange(n) * 2 * np.pi * 220 / dsp.SAMPLE_RATE)).astype(np.float32)
        return audio, [Chunk(spoken, tokens, n / dsp.SAMPLE_RATE)]

    def health(self) -> dict[str, Any]:
        return {"engine": self.name, "espeak_fallback": True, "voices": len(VOICES_BY_ID)}


@dataclass(order=True)
class _Job:
    priority: int
    seq: int
    key: str = field(compare=False)
    spoken: str = field(compare=False)
    voice: VoiceMix = field(compare=False)
    speed: float = field(compare=False)
    pitch: float = field(compare=False)
    future: asyncio.Future[Synthesis] = field(compare=False)
    waiters: int = field(default=1, compare=False)


class SynthesisWorker:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._queue: asyncio.PriorityQueue[_Job] = asyncio.PriorityQueue()
        self._inflight: dict[str, _Job] = {}
        self._seq = itertools.count()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts")
        self._task: asyncio.Task[None] | None = None
        self.stats = {"synthesized": 0, "audio_seconds": 0.0, "compute_seconds": 0.0}

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="tts-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def load(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self.engine.load)

    async def submit(
        self, key: str, spoken: str, voice: VoiceMix, speed: float, pitch: float, priority: str
    ) -> Synthesis:
        prio = PRIORITY.get(priority, 1)
        job = self._inflight.get(key)
        if job is not None:
            job.waiters += 1
            if prio < job.priority:
                # Promote: re-queue under the higher priority, the stale entry is skipped.
                job.priority = prio
                await self._queue.put(job)
        else:
            loop = asyncio.get_running_loop()
            job = _Job(
                prio, next(self._seq), key, spoken, voice, speed, pitch, loop.create_future()
            )
            self._inflight[key] = job
            await self._queue.put(job)
        try:
            return await asyncio.shield(job.future)
        except asyncio.CancelledError:
            job.waiters -= 1
            raise

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            job = await self._queue.get()
            if job.future.done() or self._inflight.get(job.key) is not job:
                continue
            if job.waiters <= 0:
                self._inflight.pop(job.key, None)
                job.future.cancel()
                continue
            try:
                result = await loop.run_in_executor(self._executor, self._compute, job)
                job.future.set_result(result)
            except Exception as exc:  # surfaced to every waiter
                log.exception("synthesis failed")
                job.future.set_exception(exc)
            finally:
                self._inflight.pop(job.key, None)

    def _compute(self, job: _Job) -> Synthesis:
        started = time.monotonic()
        p = dsp.pitch_factor(job.pitch)
        audio, chunks = self.engine.synthesize(
            job.spoken, job.voice, dsp.synthesis_speed(job.speed, job.pitch)
        )
        words = align(job.spoken, chunks)
        if abs(p - 1.0) > 1e-3:
            audio = dsp.shift_pitch(audio, job.pitch)
            words = [TimedSpan(w.spoken_start, w.spoken_end, w.start / p, w.end / p) for w in words]
        elapsed = time.monotonic() - started
        duration = len(audio) / dsp.SAMPLE_RATE
        self.stats["synthesized"] += 1
        self.stats["audio_seconds"] += duration
        self.stats["compute_seconds"] += elapsed
        log.info(
            "synth %.2fs audio in %.2fs (rtf %.2f): %.60s",
            duration,
            elapsed,
            elapsed / max(duration, 1e-3),
            job.spoken,
        )
        return Synthesis(audio, words, duration, elapsed * 1000)
