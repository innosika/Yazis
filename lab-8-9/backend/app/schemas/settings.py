"""The settings profile: one document the web app and the browser extension share."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VoiceSettings(BaseModel):
    voice: str = "af_heart"
    blend: str | None = None
    mix: float = Field(0.3, ge=0.0, le=1.0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0.0, ge=-4.0, le=4.0)
    volume: float = Field(1.0, ge=0.0, le=1.5)
    sentence_pause: float = Field(0.12, ge=0.0, le=2.0)
    paragraph_pause: float = Field(0.5, ge=0.0, le=3.0)


class ReadingSettings(BaseModel):
    citations: Literal["skip", "read"] = "skip"
    urls: Literal["skip", "link", "domain"] = "domain"
    math: Literal["verbalize", "skip"] = "verbalize"
    acronyms: Literal["auto", "spell"] = "auto"
    announce_headings: bool = True


class ListeningSettings(BaseModel):
    engine: Literal["auto", "cloud", "local"] = "auto"
    language: Literal["en", "ru", "de", "fr"] = "en"
    mode: Literal["hands-free", "push-to-talk"] = "push-to-talk"
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    confirmations: Literal["voice", "sound", "off"] = "sound"
    llm_fallback: bool = True
    system_notifications: bool = False


class Profile(BaseModel):
    voice: VoiceSettings = VoiceSettings()
    reading: ReadingSettings = ReadingSettings()
    listening: ListeningSettings = ListeningSettings()
