"""Cloud recognition: Whisper large-v3-turbo on Groq's OpenAI-compatible endpoint."""

from __future__ import annotations

import time

import httpx

from app.asr.base import AuthFailed, RateLimited, Transcript, Unavailable


class GroqASR:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.url = f"{base_url.rstrip('/')}/audio/transcriptions"
        self.name = f"groq:{model}"

    async def transcribe(self, wav: bytes, language: str | None, prompt: str) -> Transcript:
        data = {"model": self.model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as client:
                r = await client.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=data,
                    files={"file": ("utterance.wav", wav, "audio/wav")},
                )
        except httpx.HTTPError as exc:
            raise Unavailable(f"Groq unreachable: {exc.__class__.__name__}") from exc
        if r.status_code == 429:
            raise RateLimited(_retry_after(r))
        if r.status_code in (401, 403):
            raise AuthFailed("Groq rejected the API key")
        if r.status_code >= 400:
            raise Unavailable(f"Groq returned {r.status_code}: {r.text[:200]}")
        body = r.json()
        segments = body.get("segments") or []
        nsp = max((float(s.get("no_speech_prob", 0.0)) for s in segments), default=0.0)
        alp = min((float(s.get("avg_logprob", 0.0)) for s in segments), default=0.0)
        return Transcript(
            text=(body.get("text") or "").strip(),
            engine=self.name,
            language=body.get("language"),
            duration=float(body.get("duration") or 0.0),
            no_speech_prob=nsp,
            avg_logprob=alp,
            ms=(time.monotonic() - started) * 1000,
        )


def _retry_after(r: httpx.Response) -> float:
    for header in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-audio-seconds"):
        value = r.headers.get(header)
        if not value:
            continue
        try:
            return max(1.0, float(value.rstrip("s")))
        except ValueError:
            continue
    return 30.0
