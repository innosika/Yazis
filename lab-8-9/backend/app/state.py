"""Process-wide singletons, created in the FastAPI lifespan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelStatus:
    tts: str = "loading"  # loading | ready | error
    asr_local: str = "idle"  # idle | loading | ready | error
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppState:
    status: ModelStatus = field(default_factory=ModelStatus)
    tts: Any = None  # app.tts.service.TTSService
    asr: Any = None  # app.asr.router.ASRRouter
    commands: Any = None  # app.commands.service.CommandService
    llm: Any = None  # app.llm.client.GroqLLM | None


state = AppState()
