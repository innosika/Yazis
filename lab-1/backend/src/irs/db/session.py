"""Async engine, session factory and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from irs.config import settings
from irs.logging import get_logger

log = get_logger("irs.db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


# NOTE on pgvector and asyncpg.
#
# pgvector-python offers two mutually exclusive ways to handle the `vector` type:
#
#   * `pgvector.asyncpg.register_vector`, for code using asyncpg *directly*. It installs
#     a binary codec, after which asyncpg expects a Python list for every vector
#     parameter.
#   * `pgvector.sqlalchemy.VECTOR`, the SQLAlchemy column type used by our models. It
#     serialises a list to pgvector's text representation and lets PostgreSQL parse it.
#
# Installing both is a bug: the SQLAlchemy type hands asyncpg a string while the codec
# demands a list, and asyncpg rejects it with "expected list or ndarray". Since the models
# declare `VECTOR`, the codec is deliberately *not* registered — the column type is the
# single mechanism, and vectors round-trip through the text protocol.
#
# The failure only surfaced on a query that wrapped a distance expression in a subquery,
# which is why it is recorded here rather than left to be rediscovered.


def get_engine() -> AsyncEngine:
    """Process-wide engine. Created lazily so importing the package touches no sockets."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            str(settings.postgres_dsn),
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            # The crawler holds connections across awaits; recycle to survive restarts
            # of the database container during development.
            pool_recycle=1_800,
        )
        log.info(
            "engine_created",
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that commits on success, rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def session_scope() -> AsyncSession:
    """Session for use outside a request (background tasks, CLI, seeding)."""
    return get_sessionmaker()()


async def ping() -> bool:
    """Cheap liveness probe used by ``/health``."""
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        log.info("engine_disposed")
    _engine = None
    _sessionmaker = None
