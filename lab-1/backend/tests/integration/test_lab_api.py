"""Relevance Lab endpoints: projection, query ray, Rocchio rounds, replay."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete, select

from irs.db.models import FeedbackSession, Posting
from irs.db.session import dispose_engine, get_sessionmaker
from irs.main import create_app
from irs.telemetry.redis_client import close_redis
from tests.conftest import requires_database

pytestmark = [pytest.mark.integration, requires_database]


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if (await session.execute(select(Posting.term_id).limit(1))).first() is None:
            pytest.skip("index is empty — run `make seed && make index`")
        before = {row for (row,) in (await session.execute(select(FeedbackSession.id))).all()}
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test/api"
    ) as http:
        yield http
    async with sessionmaker() as session:
        statement = delete(FeedbackSession)
        if before:
            statement = statement.where(FeedbackSession.id.not_in(before))
        await session.execute(statement)
        await session.commit()
    await close_redis()
    await dispose_engine()


async def test_space_has_every_document_and_a_query_ray(client: httpx.AsyncClient) -> None:
    response = await client.get("/lab/space", params={"query": "vector space model"})
    assert response.status_code == 200, response.text
    space = response.json()
    assert space["components"] == 3
    assert 0.0 < space["explained_variance_ratio"] <= 1.0
    assert len(space["points"]) == space["document_count"] > 0
    assert space["query"]["terms_in_basis"] >= 1
    assert any(abs(v) > 0 for v in (space["query"]["x"], space["query"]["y"], space["query"]["z"]))
    ranked = [p for p in space["points"] if p["rank"] is not None]
    assert ranked and max(p["cosine"] for p in ranked) > 0


async def test_two_feedback_rounds_move_the_query(client: httpx.AsyncClient) -> None:
    first = await client.post(
        "/lab/feedback", json={"query": "vector space model", "relevant": [], "non_relevant": []}
    )
    assert first.status_code == 200, first.text
    round1 = first.json()
    assert round1["iteration"] == 1
    top = [entry["document_id"] for entry in round1["ranking"]]
    assert top

    second = await client.post(
        "/lab/feedback",
        json={
            "session_id": round1["session_id"],
            "query": "vector space model",
            "relevant": top[:2],
            "non_relevant": top[-1:],
        },
    )
    assert second.status_code == 200, second.text
    round2 = second.json()
    assert round2["iteration"] == 2
    assert round2["session_id"] == round1["session_id"]
    assert len(round2["query_terms"]) > len(round1["query_terms"])
    assert round2["added_terms"]
    assert round2["query_point"] != round1["query_point"]
    assert len(round2["history"]) == 2
    # Original query words stay marked as such among the expansion terms.
    assert any(t["is_original"] for t in round2["query_terms"])

    history = await client.get(f"/lab/feedback/{round1['session_id']}")
    assert [it["iteration"] for it in history.json()] == [1, 2]
