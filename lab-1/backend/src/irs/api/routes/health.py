"""Liveness and readiness endpoints.

``/health`` answers "is the process up" and never touches a dependency, so container
healthchecks cannot cascade. ``/health/ready`` reports each dependency separately, which
is what ``make up`` waits on and what the UI's status indicator reads.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from irs import __version__
from irs.config import settings
from irs.db import session as db
from irs.logging import get_logger
from irs.telemetry import redis_client

log = get_logger("irs.api.health")
router = APIRouter(tags=["health"])


class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    dependencies: list[DependencyStatus] = []


@router.get("/health", response_model=HealthResponse, summary="Liveness")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, environment=settings.environment)


async def _probe(name: str, coro: Any) -> DependencyStatus:
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        await asyncio.wait_for(coro, timeout=5.0)
    except Exception as exc:
        return DependencyStatus(
            name=name,
            ok=False,
            detail=f"{type(exc).__name__}: {exc}"[:200],
            latency_ms=round((loop.time() - start) * 1_000, 2),
        )
    return DependencyStatus(name=name, ok=True, latency_ms=round((loop.time() - start) * 1_000, 2))


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness")
async def ready(response: Response) -> HealthResponse:
    checks = await asyncio.gather(
        _probe("postgres", db.ping()),
        _probe("redis", redis_client.ping()),
    )
    healthy = all(c.ok for c in checks)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        log.warning("readiness_failed", failed=[c.name for c in checks if not c.ok])
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        environment=settings.environment,
        dependencies=list(checks),
    )
