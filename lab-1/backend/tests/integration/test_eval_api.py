"""End-to-end flow of the evaluation API on a throwaway topical collection.

Runs against the live compose database (``make test-all``). Everything it creates hangs
off one test collection and one test assessor, both deleted afterwards, so the real
collections are untouched. The LLM assessor is mocked: the judging job runs through the
in-memory broker with a fake verdict.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete, select

from irs.db.models import Posting, TestCollection
from irs.db.models.evaluation import Assessor
from irs.db.session import dispose_engine, get_sessionmaker
from irs.eval import assessor as assessor_module
from irs.eval.topics import TopicFile, TopicSeed, seed_topics
from irs.main import create_app
from irs.telemetry.redis_client import close_redis
from tests.conftest import requires_database

pytestmark = [pytest.mark.integration, requires_database]

TOPICS = [
    TopicSeed(1, "vector space model cosine similarity", "d", "n", "document vectors", "topical"),
    TopicSeed(2, "web crawler robots", "d", "n", "spider frontier", "topical"),
    TopicSeed(3, "punched card tabulating machine", "d", "n", "Hollerith census", "navigational"),
]


@pytest.fixture
async def collection_name() -> AsyncIterator[str]:
    """A fresh collection seeded with three topics, removed after the test."""
    name = f"test-topical-{uuid.uuid4().hex[:8]}"
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        if (await session.execute(select(Posting.term_id).limit(1))).first() is None:
            pytest.skip("index is empty — run `make seed && make index`")
        await seed_topics(session, TopicFile(name, "test", TOPICS))
        await session.commit()
    try:
        yield name
    finally:
        async with sessionmaker() as session:
            await session.execute(delete(TestCollection).where(TestCollection.name == name))
            await session.execute(delete(Assessor).where(Assessor.name.like("test-assessor-%")))
            await session.commit()
        # The engine is bound to this test's event loop; the next test gets a fresh one.
        await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as http:
        yield http
    # Module-level clients (engine, Redis) were bound to this test's event loop; a later test
    # runs on a fresh loop and must not inherit them.
    await close_redis()
    await dispose_engine()


async def _collection_id(client: httpx.AsyncClient, name: str) -> int:
    response = await client.get("/eval/collections")
    response.raise_for_status()
    return next(c["id"] for c in response.json() if c["name"] == name)


async def _poll(
    client: httpx.AsyncClient, path: str, done: str, budget_seconds: float = 120.0
) -> dict[str, object]:
    deadline = asyncio.get_running_loop().time() + budget_seconds
    while True:
        response = await client.get(path)
        response.raise_for_status()
        payload = response.json()
        rows = payload if isinstance(payload, list) else [payload]
        if all(row["status"] in (done, "failed") for row in rows):
            return {"rows": rows}
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out waiting for {path}: {rows}")
        await asyncio.sleep(0.5)


async def test_full_evaluation_flow(client: httpx.AsyncClient, collection_name: str) -> None:
    collection_id = await _collection_id(client, collection_name)
    assessor = f"test-assessor-{uuid.uuid4().hex[:6]}"

    # Selecting judged topics before the pool exists violates the anti-tuning rule.
    early = await client.post(f"/eval/collections/{collection_id}/topics/select", json={"count": 2})
    assert early.status_code == 409

    # Oracle queries are hidden until the runs are frozen.
    topics = (await client.get(f"/eval/collections/{collection_id}/topics")).json()
    assert all(t["oracle_query"] is None for t in topics)

    pool = await client.post(
        f"/eval/collections/{collection_id}/pool", json={"depth": 5, "random_size": 2}
    )
    assert pool.status_code == 200, pool.text
    built = pool.json()
    assert built["topics"] == 3
    assert set(built["by_source"]) >= {"run_union", "random_sample"}

    selected = await client.post(
        f"/eval/collections/{collection_id}/topics/select", json={"count": 2}
    )
    assert selected.status_code == 200
    assert len(selected.json()) == 2
    assert all(t["oracle_query"] for t in selected.json())

    # Blind judging: no provenance, stable order for the same assessor.
    first = await client.get(
        f"/eval/collections/{collection_id}/pool/next", params={"assessor": assessor}
    )
    assert first.status_code == 200
    pair = first.json()
    assert set(pair) == {"topic", "document", "remaining", "total", "judged_by_you", "grades"}
    for forbidden in ("source", "rank", "ranker", "score", "contributed_by"):
        assert forbidden not in pair["document"] and forbidden not in pair["topic"]
    again = await client.get(
        f"/eval/collections/{collection_id}/pool/next", params={"assessor": assessor}
    )
    assert again.json()["document"]["id"] == pair["document"]["id"]

    # Judge everything: the first two documents per topic count as relevant.
    seen: dict[int, int] = {}
    while True:
        response = await client.get(
            f"/eval/collections/{collection_id}/pool/next", params={"assessor": assessor}
        )
        if response.status_code == 204:
            break
        item = response.json()
        topic_id = item["topic"]["id"]
        seen[topic_id] = seen.get(topic_id, 0) + 1
        grade = "VITAL" if seen[topic_id] <= 2 else "NOTRELEVANT"
        posted = await client.post(
            "/eval/judgments",
            json={
                "query_id": topic_id,
                "document_id": item["document"]["id"],
                "assessor": assessor,
                "grade": grade,
                "seconds_spent": 1.5,
            },
        )
        assert posted.status_code == 200, posted.text
    assert pair["total"] == sum(seen.values())

    # A pair outside the pool is refused.
    outside = await client.post(
        "/eval/judgments",
        json={
            "query_id": topics[0]["id"],
            "document_id": 999_999_999,
            "assessor": assessor,
            "grade": "VITAL",
        },
    )
    assert outside.status_code == 422

    qrel_set = await client.post(
        f"/eval/collections/{collection_id}/qrel-sets", json={"aggregation": "or", "threshold": 1}
    )
    assert qrel_set.status_code == 200
    assert qrel_set.json()["query_count"] == 2

    started = await client.post(
        "/eval/runs",
        json={"collection_id": collection_id, "aggregation": "or", "rankers": ["vector", "bm25"]},
    )
    assert started.status_code == 202, started.text
    batch = started.json()
    run_ids = [run["id"] for run in batch["runs"]]
    assert len(run_ids) == 2

    done = await _poll(client, f"/eval/runs?batch_id={batch['batch_id']}", done="done")
    assert all(row["status"] == "done" for row in done["rows"]), done

    detail = (await client.get(f"/eval/runs/{run_ids[0]}")).json()
    keys = {row["metric_key"] for row in detail["aggregate"]}
    assert {"ap", "p_5", "p_10", "rprec", "recall", "precision", "bpref"} <= keys
    assert any(c["kind"] == "annotate" for c in detail["caveats"])

    per_query = (await client.get(f"/eval/runs/{run_ids[0]}/queries")).json()
    assert len(per_query) == 2
    aps = [q["metrics"]["ap"] for q in per_query]
    assert aps == sorted(aps)

    drill = (await client.get(f"/eval/runs/{run_ids[0]}/queries/{per_query[0]['query_id']}")).json()
    assert drill["top"] and drill["relevant_total"] == 2
    assert any(d["grade"] for d in drill["top"]) or drill["relevant_documents"]

    curves = {
        c["curve_key"]: c for c in (await client.get(f"/eval/runs/{run_ids[0]}/curves")).json()
    }
    assert {"iprec11", "iprec11_nz", "p_at_k"} <= set(curves)
    assert curves["iprec11_nz"]["support"] is not None
    assert len(curves["iprec11"]["points"]) == 11

    trec = await client.get(f"/eval/runs/{run_ids[0]}/trec")
    assert trec.status_code == 200
    assert all(len(line.split()) == 6 for line in trec.text.strip().splitlines())
    qrels_text = await client.get(f"/eval/qrel-sets/{qrel_set.json()['id']}/trec")
    assert all(len(line.split()) == 4 for line in qrels_text.text.strip().splitlines())

    compare = (await client.get(f"/eval/compare?runs={run_ids[0]},{run_ids[1]}&metric=ap")).json()
    assert compare["topic_count"] == 2
    assert compare["rows"][0]["delta_vs_baseline"] == 0.0
    assert len(compare["per_topic"]) == 2

    significance = (await client.get(f"/eval/significance?runs={run_ids[0]},{run_ids[1]}")).json()
    assert len(significance) == 1
    assert significance[0]["sample_size"] == 2
    assert "#" in significance[0]["label_a"]

    stored = (await client.get(f"/eval/runs/{run_ids[0]}/significance")).json()
    assert len(stored) == 1


async def test_llm_judging_job_is_resumable(
    client: httpx.AsyncClient, collection_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    collection_id = await _collection_id(client, collection_name)
    assert (
        await client.post(
            f"/eval/collections/{collection_id}/pool", json={"depth": 3, "random_size": 1}
        )
    ).status_code == 200
    assert (
        await client.post(f"/eval/collections/{collection_id}/topics/select", json={"count": 1})
    ).status_code == 200

    async def fake_healthcheck(self: assessor_module.LlmAssessor) -> None:
        self.model_digest = "test"

    async def fake_judge(
        self: assessor_module.LlmAssessor,
        topic: assessor_module.TopicView,
        document: assessor_module.DocumentView,
    ) -> assessor_module.Verdict:
        return assessor_module.Verdict(
            grade=assessor_module.RelevanceGrade.RELEVANT_MINUS,
            reason="test",
            raw="{}",
            seconds=0.01,
            attempts=1,
        )

    monkeypatch.setattr(assessor_module.LlmAssessor, "healthcheck", fake_healthcheck)
    monkeypatch.setattr(assessor_module.LlmAssessor, "judge", fake_judge)

    started = await client.post(f"/eval/collections/{collection_id}/judging", json={})
    assert started.status_code == 202, started.text
    job = started.json()
    assert job["total_pairs"] > 0

    finished = await _poll(client, f"/eval/judging/jobs/{job['id']}", done="done")
    row = finished["rows"][0]
    assert row["status"] == "done"
    assert row["judged_pairs"] == job["total_pairs"]
    assert row["failed_pairs"] == 0
    assert row["pending_pairs"] == 0

    # Nothing left: a second job completes immediately with zero work.
    again = (await client.post(f"/eval/collections/{collection_id}/judging", json={})).json()
    assert again["total_pairs"] == 0 and again["status"] == "done"

    collection = (await client.get(f"/eval/collections/{collection_id}")).json()
    assert collection["grade_counts"].get("RELEVANT_MINUS") == job["total_pairs"]
    assert any(a["kind"] == "llm" for a in collection["assessors"])
