"""Test fixtures.

The linguistic resources are loaded once for the whole session: spaCy and pymorphy3 each
take a couple of seconds and several hundred megabytes, and reloading them per test would
make the suite unusable.

Database-backed tests use the service container Compose already provides. The dictionary
tests that need real data read the seeded dictionary; the pipeline tests build a lexicon
from literal records instead, so they run with no database at all.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.mt.analysis import Analyzer
from app.mt.morphgen import MorphGenerator


@pytest.fixture(scope="session")
def analyzer() -> Analyzer:
    return Analyzer()


@pytest.fixture(scope="session")
def morph() -> MorphGenerator:
    return MorphGenerator()


@pytest.fixture(scope="session")
def pipeline(analyzer: Analyzer, morph: MorphGenerator):
    from app.mt.pipeline import Pipeline

    return Pipeline(analyzer, morph)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    """A fresh engine per test, with no connection pool.

    pytest-asyncio gives every test its own event loop, and an asyncpg connection belongs
    to the loop that opened it. Sharing the application's pooled engine across tests
    therefore hands the second test a connection bound to a loop that has already closed.
    `NullPool` opens and closes a connection per use, which removes the problem entirely -
    at a cost that does not matter in a test suite.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    test_engine = create_async_engine(settings.postgres_dsn, poolclass=NullPool)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(analyzer: Analyzer, morph: MorphGenerator, engine) -> AsyncIterator:
    """An HTTP client against the real app, with the resources already loaded.

    The app's lifespan is bypassed - loading spaCy per test would dominate the suite's
    runtime - so the resources are injected and the session dependency is pointed at the
    per-test engine.
    """
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app import state
    from app.db.base import get_session
    from app.main import app

    state._analyzer = analyzer
    state._morph = morph
    state._ready = True

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override() -> AsyncIterator[AsyncSession]:
        async with factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
