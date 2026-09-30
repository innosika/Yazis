"""Голосовая диктовка: аудио → текст через Groq Whisper (whisper-large-v3).

Язык в запросе НЕ указываем: Whisper сам определяет его при транскрипции, а мы затем
распознаём язык полученного текста собственными методами и сравниваем с ответом Whisper.
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import GROQ_API_KEY, GROQ_WHISPER_MODEL

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class VoiceError(Exception):
    pass


async def transcribe(audio: bytes, filename: str, content_type: str) -> dict[str, Any]:
    if not GROQ_API_KEY:
        raise VoiceError("Ключ GROQ_API_KEY не задан. Укажите его в файле .env и перезапустите: make restart")
    if len(audio) < 1000:
        raise VoiceError("Запись слишком короткая или пустая — попробуйте ещё раз")
    files = {"file": (filename, audio, content_type or "application/octet-stream")}
    data = {"model": GROQ_WHISPER_MODEL, "response_format": "verbose_json", "temperature": "0"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                                 files=files, data=data)
    if resp.status_code != 200:
        raise VoiceError(f"Groq API вернул {resp.status_code}: {resp.text[:300]}")
    payload = resp.json()
    return {"text": (payload.get("text") or "").strip(),
            "whisper_language": payload.get("language"),
            "duration": payload.get("duration")}
