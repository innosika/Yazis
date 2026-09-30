"""Choose the recogniser for each utterance and fall back when the cloud fails.

* ``auto``: Groq when a key is configured and the circuit is closed, local otherwise.
* While Lector is speaking the utterance always goes to the local engine: most of those
  captures are echo, and each cloud request is billed as at least ten seconds.
* A 429 opens the circuit for the server's ``retry-after``; a network error for a
  minute; a rejected key until restart. Every fallback is reported back as a note the
  interface shows, so the user always knows which engine answered.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from app.asr.base import ASRError, AuthFailed, RateLimited, Transcript, Unavailable

log = logging.getLogger(__name__)


class Recognizer(Protocol):
    name: str

    async def transcribe(self, wav: bytes, language: str | None, prompt: str) -> Transcript: ...


@dataclass
class CircuitState:
    open_until: float = 0.0
    reason: str = ""
    permanent: bool = False

    def is_open(self) -> bool:
        return self.permanent or time.monotonic() < self.open_until

    def trip(self, seconds: float, reason: str, permanent: bool = False) -> None:
        self.open_until = time.monotonic() + seconds
        self.reason = reason
        self.permanent = permanent

    def remaining(self) -> float:
        return max(0.0, self.open_until - time.monotonic())


class ASRRouter:
    def __init__(self, cloud: Recognizer | None, local: Recognizer | None) -> None:
        self.cloud = cloud
        self.local = local
        self.circuit = CircuitState()

    def status(self) -> dict[str, object]:
        return {
            "cloud": None if self.cloud is None else self.cloud.name,
            "local": None if self.local is None else self.local.name,
            "cloud_available": self.cloud is not None and not self.circuit.is_open(),
            "cloud_cooldown_s": round(self.circuit.remaining(), 1),
            "cloud_issue": self.circuit.reason or None,
        }

    def pick(self, preference: str, playing: bool) -> tuple[Recognizer, list[str]]:
        notes: list[str] = []
        want_cloud = preference in ("auto", "cloud") and not playing
        if want_cloud and self.cloud is not None and not self.circuit.is_open():
            return self.cloud, notes
        if want_cloud and preference == "cloud":
            if self.cloud is None:
                notes.append("No Groq key configured — using the local recogniser")
            elif self.circuit.is_open():
                notes.append(_cooldown_note(self.circuit))
        if self.local is None:
            if self.cloud is None:
                raise Unavailable("No speech recogniser is available")
            return self.cloud, notes
        return self.local, notes

    async def transcribe(
        self,
        wav: bytes,
        language: str | None,
        prompt: str,
        preference: str = "auto",
        playing: bool = False,
    ) -> Transcript:
        engine, notes = self.pick(preference, playing)
        try:
            t = await engine.transcribe(wav, language, prompt)
        except ASRError as exc:
            if engine is not self.cloud or self.local is None:
                raise
            self._trip(exc)
            notes.append(_cooldown_note(self.circuit))
            log.warning("cloud recognition failed (%s); falling back to local", exc)
            t = await self.local.transcribe(wav, language, prompt)
        t.notes = notes + t.notes
        return t

    def _trip(self, exc: ASRError) -> None:
        if isinstance(exc, RateLimited):
            self.circuit.trip(exc.retry_after, "rate limit")
        elif isinstance(exc, AuthFailed):
            self.circuit.trip(0, "invalid API key", permanent=True)
        else:
            self.circuit.trip(60, "cloud unreachable")


def _cooldown_note(c: CircuitState) -> str:
    if c.permanent:
        return "Groq rejected the API key — using the local recogniser"
    return f"Cloud cooling down ({c.reason}, {c.remaining():.0f} s) — using local"
