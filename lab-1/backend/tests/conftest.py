"""Shared test fixtures."""

from __future__ import annotations

import os

# Must be set before `irs.config` is imported, so the settings singleton picks it up.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_STREAM_ENABLED", "false")

import pytest


@pytest.fixture(scope="session")
def hand_corpus() -> dict[str, dict[str, int]]:
    """A three-document collection small enough to verify entirely by hand.

    Term frequencies are given directly rather than produced by the NLP pipeline, so
    that these tests exercise the arithmetic in isolation from lemmatisation.

    Layout chosen so that two independent things can be checked:

    * ``d1`` and ``d2`` contain only terms of *equal* document frequency, so the IDF
      factors cancel in the normalisation and the expected weights have exact closed
      forms — which is what makes the logarithm-base invariance visible.
    * ``d3`` mixes a rare term with a common one, so it exercises the general case
      where no cancellation occurs.
    """
    return {
        "d1": {"vector": 3, "model": 2, "search": 1},
        "d2": {"vector": 1, "search": 2},
        "d3": {"model": 1, "engine": 4},
    }


@pytest.fixture(scope="session")
def hand_document_frequencies() -> dict[str, int]:
    """`N_k` for :func:`hand_corpus`. vector/model/search in 2 documents, engine in 1."""
    return {"vector": 2, "model": 2, "search": 2, "engine": 1}


# --------------------------------------------------------------------------------
# Integration fixtures — these require a live PostgreSQL with pgvector.
#
# The DSN comes from POSTGRES_DSN. When it is absent the integration tests are skipped
# rather than failed, so `make test` stays runnable with no services up while
# `make test-all` exercises the full stack.
# --------------------------------------------------------------------------------

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402


def _database_configured() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


requires_database = pytest.mark.skipif(
    not _database_configured(),
    reason="POSTGRES_DSN is not set; run via `make test-all`",
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:  # type: ignore[name-defined] # noqa: F821
    """A session that is rolled back at the end of the test.

    Every test therefore starts from the same committed state and cannot leak rows into
    the next one, without paying to recreate the schema per test.
    """
    from irs.db.session import dispose_engine, get_sessionmaker

    async with get_sessionmaker()() as active:
        try:
            yield active
        finally:
            await active.rollback()
    await dispose_engine()
