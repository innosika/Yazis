"""Text in, speech out: normalize, look up the cache or synthesize, map words back."""

from __future__ import annotations

import asyncio
import hashlib

from app.schemas.tts import SynthesizeRequest, SynthesizeResponse, Word
from app.text.normalize import NORMALIZER_VERSION, Context, SpokenText, normalize
from app.tts import dsp
from app.tts.align import TimedSpan
from app.tts.cache import AudioCache, cache_key
from app.tts.engine import SynthesisWorker, VoiceMix
from app.tts.voices import get_voice


class TTSService:
    def __init__(self, worker: SynthesisWorker, cache: AudioCache) -> None:
        self.worker = worker
        self.cache = cache
        self.lexicon: dict[str, str] = {}
        self.lexicon_version = "0"

    def set_lexicon(self, entries: dict[str, str]) -> None:
        self.lexicon = dict(entries)
        digest = hashlib.sha1(repr(sorted(entries.items())).encode()).hexdigest()[:12]
        self.lexicon_version = digest

    def context(self, req: SynthesizeRequest) -> Context:
        o = req.options
        return Context(
            citations=o.citations,
            urls=o.urls,
            math=o.math,
            acronyms=o.acronyms,
            heading=req.kind == "heading" and o.announce_headings,
            lexicon=self.lexicon,
        )

    def spoken(self, req: SynthesizeRequest) -> SpokenText:
        return normalize(req.text, self.context(req))

    async def synthesize(self, req: SynthesizeRequest) -> SynthesizeResponse:
        get_voice(req.voice.id)
        if req.voice.blend:
            get_voice(req.voice.blend)
        spoken = self.spoken(req)
        text = spoken.text or "."
        voice = VoiceMix(req.voice.id, req.voice.blend, req.voice.mix)
        key = cache_key(
            self.worker.engine.name,
            NORMALIZER_VERSION,
            self.lexicon_version,
            voice.key(),
            round(req.speed, 2),
            round(req.pitch, 1),
            text,
        )
        hit = self.cache.get(key)
        if hit is not None:
            return self._response(key, spoken, hit.duration, hit.words, cached=True, ms=0.0)
        result = await self.worker.submit(key, text, voice, req.speed, req.pitch, req.priority)
        # Cache writes go to a thread: a WAV is ~50 KB per second of speech.
        wav = dsp.to_wav(result.audio)
        await asyncio.to_thread(self.cache.put, key, wav, result.duration, result.words)
        return self._response(key, spoken, result.duration, result.words, False, result.compute_ms)

    @staticmethod
    def _response(
        key: str,
        spoken: SpokenText,
        duration: float,
        words: list[TimedSpan],
        cached: bool,
        ms: float,
    ) -> SynthesizeResponse:
        out: list[Word] = []
        last: tuple[int, int] | None = None
        for w in words:
            span = spoken.source_span(w.spoken_start, w.spoken_end)
            if span is None:
                continue
            # Several spoken words from one replacement ("big O of n squared") share the
            # whole source expression; merge them into one highlight.
            if last == span and out:
                out[-1].end = round(w.end, 3)
                out[-1].text += " " + spoken.text[w.spoken_start : w.spoken_end]
                continue
            out.append(
                Word(
                    text=spoken.text[w.spoken_start : w.spoken_end],
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    src_start=span[0],
                    src_end=span[1],
                )
            )
            last = span
        return SynthesizeResponse(
            id=key,
            audio_url=f"/api/tts/audio/{key}.wav",
            duration=round(duration, 3),
            spoken=spoken.text,
            words=out,
            cached=cached,
            compute_ms=round(ms, 1),
        )
