"""Lector API: speech synthesis, speech recognition and voice commands for CS papers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_assist,
    routes_commands,
    routes_documents,
    routes_health,
    routes_lexicon,
    routes_settings,
    routes_tts,
    routes_voice,
)
from app.asr.groq import GroqASR
from app.asr.local import ParakeetASR
from app.asr.router import ASRRouter
from app.commands.llm import LLMIntent
from app.commands.service import CommandService
from app.config import settings
from app.db.base import init_db
from app.llm.client import GroqLLM
from app.schemas.tts import SynthesizeRequest
from app.state import state
from app.tts.cache import AudioCache
from app.tts.engine import Engine, FakeEngine, KokoroEngine, SynthesisWorker
from app.tts.service import TTSService

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("lector")


async def _after(first: asyncio.Task[None], then: object) -> None:
    await asyncio.wait({first})
    await then()  # type: ignore[operator]


async def _load_tts(worker: SynthesisWorker) -> None:
    try:
        await worker.load()
        # Warm-up: the first inference pays for graph set-up and G2P model loading.
        await state.tts.synthesize(SynthesizeRequest(text="Lector is ready.", priority="now"))
        state.status.tts = "ready"
        state.status.detail["tts_engine"] = worker.engine.health()
        log.info("speech synthesis ready")
    except Exception as exc:
        log.exception("speech synthesis failed to load")
        state.status.tts = "error"
        state.status.detail["tts_error"] = str(exc)


class _FakeASR:
    """Test double: the WAV's first bytes after the header carry nothing; tests patch it."""

    name = "fake:asr"

    async def transcribe(self, wav: bytes, language: str | None, prompt: str):  # type: ignore[no-untyped-def]
        from app.asr.base import Transcript

        return Transcript(
            text=_FakeASR.next_text, engine=self.name, language=language, duration=1.0
        )

    next_text = ""


def _build_voice() -> None:
    cloud = (
        GroqASR(settings.groq_api_key, settings.groq_asr_model, settings.groq_base_url)
        if settings.has_groq
        else None
    )
    local: object
    if settings.fake_engines:
        local = _FakeASR()
    else:
        parakeet = ParakeetASR(settings.parakeet_dir)
        local = parakeet
        state.status.detail["asr_local_model"] = parakeet.name
    state.asr = ASRRouter(cloud, local)  # type: ignore[arg-type]
    state.llm = (
        GroqLLM(settings.groq_api_key, settings.groq_llm_model, settings.groq_base_url)
        if settings.has_groq
        else None
    )
    state.commands = CommandService(state.asr, LLMIntent(state.llm) if state.llm else None)


async def _warm_local_asr() -> None:
    local = state.asr.local if state.asr else None
    if not isinstance(local, ParakeetASR):
        state.status.asr_local = "ready" if local is not None else "off"
        return
    state.status.asr_local = "loading"
    try:
        await asyncio.to_thread(local.load)
        state.status.asr_local = "ready"
    except Exception as exc:
        log.exception("local recogniser failed to load")
        state.status.asr_local = "error"
        state.status.detail["asr_local_error"] = str(exc)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db(settings.db_path)
    engine: Engine = (
        FakeEngine()
        if settings.fake_engines
        else KokoroEngine(settings.kokoro_repo, settings.tts_threads)
    )
    worker = SynthesisWorker(engine)
    worker.start()
    state.tts = TTSService(worker, AudioCache(settings.cache_dir, settings.tts_cache_limit_mb))
    routes_lexicon.refresh()
    routes_documents.seed_sample()
    _build_voice()
    loader = asyncio.create_task(_load_tts(worker))
    # The local recogniser loads after the voice so first audio is not delayed.
    asr_loader = asyncio.create_task(_after(loader, _warm_local_asr))
    log.info("Lector API started (engines: %s)", "fake" if settings.fake_engines else "real")
    yield
    loader.cancel()
    asr_loader.cancel()
    await worker.stop()


app = FastAPI(
    title="Lector API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
# The SPA is served same-origin through nginx; CORS is only for `npm run dev`.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for r in (
    routes_health,
    routes_tts,
    routes_documents,
    routes_voice,
    routes_commands,
    routes_assist,
    routes_settings,
    routes_lexicon,
):
    app.include_router(r.router, prefix="/api")
