"""FastAPI application: machine translation workbench, English -> Russian.

Lab 4, variant 1. See SPEC.md for the requirement-to-module map.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import state
from app.api import (
    routes_dictionary,
    routes_export,
    routes_health,
    routes_memory,
    routes_meta,
    routes_translate,
)
from app.config import settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("loading linguistic resources")
    state.init()
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    log.info("ready")
    yield
    from app.db.base import engine

    await engine.dispose()


app = FastAPI(
    title="Machine Translation Workbench",
    description=(
        "English to Russian rule-based machine translation with a PostgreSQL dictionary, "
        "domain-aware word-sense disambiguation and a translation memory."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# The frontend is served from the same origin by nginx in production; CORS is open only so
# `npm run dev` on the host can talk to the container.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router, prefix="/api")
app.include_router(routes_meta.router, prefix="/api")
app.include_router(routes_translate.router, prefix="/api")
app.include_router(routes_dictionary.router, prefix="/api")
app.include_router(routes_memory.router, prefix="/api")
app.include_router(routes_export.router, prefix="/api")
