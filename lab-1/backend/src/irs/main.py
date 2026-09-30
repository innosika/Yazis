"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from irs import __version__
from irs.api.router import api_router
from irs.config import settings
from irs.db import session as db
from irs.logging import Stopwatch, bind_request_id, configure_logging, get_logger
from irs.telemetry import metrics, redis_client
from irs.telemetry.logstream import publisher

log = get_logger("irs.app")

#: Paths excluded from access logging — they are polled by the container healthcheck
#: every few seconds and would otherwise drown the log console.
_QUIET_PATHS = frozenset({"/api/health", "/metrics", "/api/stream/logs"})


async def _warm_models() -> None:
    """Pre-load the spaCy pipeline off the event loop."""
    try:
        from irs.nlp.pipeline import analyzer

        await asyncio.to_thread(analyzer.warm)
        log.info("nlp_warm")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("nlp_warm_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log.info(
        "startup",
        version=__version__,
        environment=settings.environment,
        log_level=settings.log_level,
        semantic_enabled=settings.semantic.enabled,
        log_base=settings.index.log_base,
    )
    await publisher.start()

    # Load the linguistic model in the background. It takes a second or two, which would
    # otherwise be paid by whoever runs the first search; doing it here means /health
    # answers immediately while the model loads in parallel.
    warm_task = asyncio.create_task(_warm_models(), name="warm-models")

    yield

    warm_task.cancel()
    log.info("shutdown")
    await publisher.stop()
    await redis_client.close_redis()
    await db.dispose_engine()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Information retrieval system implementing the vector search model "
            "(TF-IDF term weights, cosine similarity) over a web-crawled English "
            "document collection, with a programmatic quality-evaluation module."
        ),
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    @app.middleware("http")
    async def correlate_and_time(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Bind a correlation id to the request and log its outcome and duration."""
        incoming = request.headers.get("X-Request-ID")
        with bind_request_id(incoming) as request_id:
            watch = Stopwatch()
            quiet = request.url.path in _QUIET_PATHS
            try:
                response = await call_next(request)
            except Exception:
                log.exception(
                    "request_failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=watch.total_ms,
                )
                raise
            duration_ms = watch.total_ms
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
            if not quiet:
                log.info(
                    "request",
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
            return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        log.warning("request_validation_failed", errors=exc.errors())
        return ORJSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": 422,
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        # Detail is withheld in production but always present in the log.
        log.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        message = f"{type(exc).__name__}: {exc}" if settings.is_dev else "Internal server error"
        return ORJSONResponse(status_code=500, content={"error": {"code": 500, "message": message}})

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        payload, content_type = metrics.render_latest()
        return Response(content=payload, media_type=content_type)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/api/docs",
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    return app


app = create_app()
