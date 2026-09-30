"""LLM assessor: prompt shape, grade parsing and transport behaviour (mocked)."""

from __future__ import annotations

import httpx
import pytest
import respx

from irs.config import AssessorSettings
from irs.db.models.enums import RelevanceGrade
from irs.eval.assessor import (
    AssessorError,
    DocumentView,
    LlmAssessor,
    TopicView,
    build_prompt,
    parse_grade,
)

BASE = "http://llm.test/v1"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"grade": "RELEVANT_PLUS", "reason": "explains it"}', RelevanceGrade.RELEVANT_PLUS),
        ('Sure! {"grade":"VITAL","reason":"x"} thanks', RelevanceGrade.VITAL),
        ('{"grade": 2, "reason": "numeric"}', RelevanceGrade.RELEVANT_PLUS),
        ("Grade: NOTRELEVANT — the page is about looms.", RelevanceGrade.NOTRELEVANT),
        ("**relevant-** it barely mentions it", RelevanceGrade.RELEVANT_MINUS),
        ("I would say relevant+ here", RelevanceGrade.RELEVANT_PLUS),
        ("cant be judged, the text is empty", RelevanceGrade.CANTBEJUDGED),
        ("grade = 3", RelevanceGrade.VITAL),
    ],
)
def test_parse_grade_accepts_the_shapes_models_produce(text: str, expected: RelevanceGrade) -> None:
    parsed = parse_grade(text)
    assert parsed is not None
    assert parsed[0] is expected


def test_parse_grade_keeps_the_json_reason() -> None:
    parsed = parse_grade('{"grade": "VITAL", "reason": "directly about BM25"}')
    assert parsed == (RelevanceGrade.VITAL, "directly about BM25")


def test_parse_grade_rejects_ambiguous_answers() -> None:
    assert parse_grade("It is VITAL or maybe NOTRELEVANT, hard to say") is None
    assert parse_grade("no idea") is None


def test_prompt_shows_topic_and_document_but_never_ranker_or_rank() -> None:
    messages = build_prompt(
        TopicView("okapi bm25", "desc", "narr"),
        DocumentView("Okapi BM25", "https://x/y", "passage text"),
    )
    assert [m["role"] for m in messages] == ["system", "user"]
    joined = " ".join(m["content"] for m in messages)
    for label in ("VITAL", "RELEVANT_PLUS", "RELEVANT_MINUS", "NOTRELEVANT", "CANTBEJUDGED"):
        assert label in joined
    assert "narr" in joined and "passage text" in joined
    for forbidden in ("rank", "score", "bm25 ranker", "vector model"):
        assert forbidden not in messages[1]["content"].lower()


def _assessor(max_retries: int = 3) -> LlmAssessor:
    config = AssessorSettings(
        base_url=BASE, model="test-model", max_retries=max_retries, timeout_seconds=5
    )
    client = httpx.AsyncClient(base_url=BASE)
    return LlmAssessor(config, client=client)


def _completion(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@respx.mock(base_url=BASE)
async def test_judge_posts_model_and_temperature_and_returns_verdict(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post("/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_completion('{"grade":"RELEVANT_MINUS","reason":"brief"}')
        )
    )
    assessor = _assessor()
    verdict = await assessor.judge(TopicView("t", None, None), DocumentView("d", "u", "p"))

    assert verdict.grade is RelevanceGrade.RELEVANT_MINUS
    assert verdict.reason == "brief"
    assert verdict.attempts == 1
    body = route.calls.last.request.read()
    assert b'"model": "test-model"' in body or b'"model":"test-model"' in body
    assert b"temperature" in body


@respx.mock(base_url=BASE)
async def test_judge_retries_after_server_error(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(LlmAssessor, "_backoff", staticmethod(no_sleep))
    respx_mock.post("/chat/completions").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json=_completion('{"grade":"VITAL","reason":"ok"}')),
        ]
    )
    verdict = await _assessor().judge(TopicView("t", None, None), DocumentView("d", "u", "p"))
    assert verdict.attempts == 2
    assert verdict.grade is RelevanceGrade.VITAL


@respx.mock(base_url=BASE)
async def test_judge_gives_up_after_max_retries(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(LlmAssessor, "_backoff", staticmethod(no_sleep))
    respx_mock.post("/chat/completions").mock(return_value=httpx.Response(503))
    with pytest.raises(AssessorError):
        await _assessor(max_retries=2).judge(
            TopicView("t", None, None), DocumentView("d", "u", "p")
        )


@respx.mock(base_url=BASE)
async def test_client_error_is_fatal_without_retry(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post("/chat/completions").mock(
        return_value=httpx.Response(404, text="no model")
    )
    with pytest.raises(AssessorError):
        await _assessor().judge(TopicView("t", None, None), DocumentView("d", "u", "p"))
    assert route.call_count == 1


@respx.mock(base_url=BASE)
async def test_unparseable_answers_are_retried_then_fail(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_sleep(_: int) -> None:
        return None

    monkeypatch.setattr(LlmAssessor, "_backoff", staticmethod(no_sleep))
    respx_mock.post("/chat/completions").mock(
        return_value=httpx.Response(200, json=_completion("hmm"))
    )
    with pytest.raises(AssessorError):
        await _assessor(max_retries=2).judge(
            TopicView("t", None, None), DocumentView("d", "u", "p")
        )


@respx.mock(base_url=BASE)
async def test_healthcheck_reports_missing_model(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "other:latest"}]})
    )
    with pytest.raises(AssessorError, match="llm-pull"):
        await _assessor().healthcheck()


@respx.mock(base_url=BASE)
async def test_healthcheck_accepts_tagged_model_and_records_digest(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/models").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "test-model:latest", "digest": "abc"}]}
        )
    )
    assessor = _assessor()
    await assessor.healthcheck()
    assert assessor.model_digest == "abc"
    assert assessor.meta()["model"] == "test-model"
