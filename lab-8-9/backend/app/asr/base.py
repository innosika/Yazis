from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Transcript:
    text: str
    engine: str  # "groq:whisper-large-v3-turbo" | "local:parakeet-tdt-0.6b-v3"
    language: str | None = None
    duration: float = 0.0
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0
    ms: float = 0.0
    notes: list[str] = field(default_factory=list)


class ASRError(Exception):
    """Recognition failed in a way the user should hear about."""


class RateLimited(ASRError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class AuthFailed(ASRError):
    pass


class Unavailable(ASRError):
    pass
