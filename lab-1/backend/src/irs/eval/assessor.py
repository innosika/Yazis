"""The LLM assessor: a language model judging (topic, document) pairs on ROMIP's scale.

ROMIP judged with people. This lab has one student and roughly a thousand pairs, so the
pool is judged by a local language model instead — an accepted practice in current IR
evaluation, *provided* it is done honestly:

* the assessor is recorded as ``kind = llm`` with the model name and digest, the prompt
  version and the decoding parameters, so the report can state exactly what judged;
* every verdict keeps the model's one-sentence reason, so any single judgment can be
  audited;
* the model sees exactly what a human assessor would — the topic's title, description
  and narrative, and the document — never a ranker name, a rank or a score;
* it answers on ROMIP's five-point scale verbatim; binarisation happens at scoring time
  exactly as for human grades;
* agreement with humans is *not measured* in this lab, and the report says so.

The client speaks the OpenAI chat-completions protocol, which the ``ollama`` compose
service implements locally; any compatible endpoint can be configured instead.
"""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
import time
from dataclasses import dataclass
from typing import Any

import httpx

from irs.config import AssessorSettings, settings
from irs.db.models.enums import RelevanceGrade
from irs.logging import get_logger
from irs.selection.snippet import build_snippet

log = get_logger("irs.eval.assessor")


class AssessorError(RuntimeError):
    """The model could not be reached or did not produce a usable grade."""


@dataclass(slots=True)
class Verdict:
    grade: RelevanceGrade
    reason: str
    raw: str
    seconds: float
    attempts: int


@dataclass(slots=True)
class TopicView:
    title: str
    description: str | None
    narrative: str | None


@dataclass(slots=True)
class DocumentView:
    title: str
    url: str
    passage: str


#: The scale, in the order the model is asked to consider it.
GRADE_GLOSS: tuple[tuple[RelevanceGrade, str, str], ...] = (
    (RelevanceGrade.VITAL, "соответствующий", "directly and substantially about the topic"),
    (
        RelevanceGrade.RELEVANT_PLUS,
        "скорее соответствующий",
        "clearly useful for the topic, though not its main subject",
    ),
    (
        RelevanceGrade.RELEVANT_MINUS,
        "возможно соответствующий",
        "touches the topic only marginally or in passing",
    ),
    (RelevanceGrade.NOTRELEVANT, "не соответствующий", "does not help with the topic"),
    (
        RelevanceGrade.CANTBEJUDGED,
        "документ не может быть оценен",
        "the text is unusable (empty, garbled, wrong language)",
    ),
)

SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are a relevance assessor for an information-retrieval evaluation, following the
    methodology of the ROMIP 2004 evaluation seminar. You will be shown a search topic —
    a short query, a description of what the user wants, and a narrative saying what
    counts as relevant — and one document from the collection.

    Judge how well the DOCUMENT satisfies the TOPIC's information need, on this scale:
    {scale}

    Rules:
    - Judge only from the text shown. Do not assume content beyond it.
    - Use the narrative to decide borderline cases; it is the authority.
    - Grade the document's usefulness for the topic, not its overall quality.
    - Answer with a single JSON object and nothing else:
      {{"grade": "<one of the five labels exactly as written>", "reason": "<one sentence>"}}
    """
)

USER_PROMPT = textwrap.dedent(
    """\
    TOPIC
    Query: {title}
    Description: {description}
    Narrative: {narrative}

    DOCUMENT
    Title: {doc_title}
    URL: {doc_url}
    Text:
    {passage}

    Respond with the JSON object only.
    """
)

_LABELS = {grade.value: grade for grade in RelevanceGrade}
_LABEL_PATTERN = re.compile(
    r"\b(VITAL|RELEVANT[_ ]?PLUS|RELEVANT[_ ]?MINUS|RELEVANT\s*\+|RELEVANT\s*-|"
    r"NOT[_ ]?RELEVANT|CAN'?T[_ ]?BE[_ ]?JUDGED)(?![A-Za-z])",
    re.IGNORECASE,
)
_NUMERIC = {
    "3": RelevanceGrade.VITAL,
    "2": RelevanceGrade.RELEVANT_PLUS,
    "1": RelevanceGrade.RELEVANT_MINUS,
    "0": RelevanceGrade.NOTRELEVANT,
}


def scale_text() -> str:
    return "\n".join(
        f"    - {grade.value}: {gloss} ({russian})" for grade, russian, gloss in GRADE_GLOSS
    )


def build_prompt(topic: TopicView, document: DocumentView) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(scale=scale_text())},
        {
            "role": "user",
            "content": USER_PROMPT.format(
                title=topic.title,
                description=topic.description or "—",
                narrative=topic.narrative or "—",
                doc_title=document.title,
                doc_url=document.url,
                passage=document.passage,
            ),
        },
    ]


def _normalise_label(token: str) -> RelevanceGrade | None:
    cleaned = re.sub(r"[\s_]+", "", token.upper())
    mapping = {
        "VITAL": RelevanceGrade.VITAL,
        "RELEVANTPLUS": RelevanceGrade.RELEVANT_PLUS,
        "RELEVANT+": RelevanceGrade.RELEVANT_PLUS,
        "RELEVANTMINUS": RelevanceGrade.RELEVANT_MINUS,
        "RELEVANT-": RelevanceGrade.RELEVANT_MINUS,
        "NOTRELEVANT": RelevanceGrade.NOTRELEVANT,
        "CANTBEJUDGED": RelevanceGrade.CANTBEJUDGED,
    }
    return mapping.get(cleaned)


def parse_grade(text: str) -> tuple[RelevanceGrade, str] | None:
    """Extract ``(grade, reason)`` from the model's answer, or ``None`` if ambiguous.

    JSON is tried first (the whole text, then the first ``{...}`` block). Failing that,
    a single scale label anywhere in the text is accepted, as is a bare digit 0–3 after
    the word "grade". Two *different* labels without JSON structure is ambiguous.
    """
    candidates = [text.strip()]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict) and "grade" in payload:
            grade_value = str(payload["grade"])
            grade = _normalise_label(grade_value) or _NUMERIC.get(grade_value.strip())
            if grade is not None:
                return grade, str(payload.get("reason", "")).strip()

    found = {
        label for label in (_normalise_label(m) for m in _LABEL_PATTERN.findall(text)) if label
    }
    if len(found) == 1:
        return found.pop(), text.strip()[:500]

    digit = re.search(r"grade\D{0,10}([0-3])\b", text, re.IGNORECASE)
    if not found and digit:
        return _NUMERIC[digit.group(1)], text.strip()[:500]
    return None


async def select_passage(text: str, title: str, lemmas: list[str], budget: int) -> str:
    """Lead of the document plus a query-biased window, within ``budget`` characters.

    The lead says what the page is about; the window shows where the topic's words occur.
    Both are what a human assessor would skim first. The window search runs spaCy, so it
    goes through a thread like every other linguistic pass.
    """
    body = (text or "").strip()
    if len(body) <= budget:
        return body
    lead_chars = budget // 3
    lead = body[:lead_chars]
    window_chars = budget - lead_chars
    try:
        snippet = await asyncio.to_thread(build_snippet, body, title, lemmas, window_chars)
        window = snippet.text
    except Exception as exc:  # the passage is a convenience; never fail the judgment on it
        log.debug("passage_window_failed", error=str(exc))
        window = ""
    if not window or window.strip("… ") in lead:
        return body[:budget]
    return f"{lead}\n[…]\n{window}"


class LlmAssessor:
    """Chat-completions client that returns ROMIP grades."""

    def __init__(
        self, config: AssessorSettings | None = None, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config or settings.assessor
        self._client = client
        self._owns_client = client is None
        self.model_digest: str | None = None

    @property
    def assessor_name(self) -> str:
        return f"llm:{self.config.model}:{self.config.prompt_version}"

    def meta(self) -> dict[str, Any]:
        return {
            "model": self.config.model,
            "model_digest": self.model_digest,
            "prompt_version": self.config.prompt_version,
            "temperature": self.config.temperature,
            "max_document_chars": self.config.max_document_chars,
            "endpoint": _host_only(self.config.base_url),
            "protocol": "openai-chat-completions",
        }

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                timeout=httpx.Timeout(self.config.timeout_seconds, connect=10.0),
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def healthcheck(self) -> None:
        """Confirm the endpoint answers and the model exists. Raises :class:`AssessorError`."""
        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AssessorError(
                f"LLM endpoint {self.config.base_url} is unreachable ({exc}). Start it with "
                "`make llm-up` (compose profile `llm`) or point ASSESSOR_LLM_BASE_URL elsewhere."
            ) from exc

        models = payload.get("data", []) if isinstance(payload, dict) else []
        names = {str(m.get("id", "")) for m in models if isinstance(m, dict)}
        wanted = self.config.model
        matched = (
            wanted in names
            or f"{wanted}:latest" in names
            or any(n.split(":")[0] == wanted.split(":")[0] and wanted in n for n in names)
        )
        if names and not matched:
            raise AssessorError(
                f"model {wanted!r} is not available at {self.config.base_url} (have: "
                f"{sorted(names)[:8]}). Pull it with `make llm-pull`."
            )
        for entry in models:
            if isinstance(entry, dict) and str(entry.get("id", "")).startswith(wanted):
                digest = entry.get("digest") or entry.get("sha256")
                self.model_digest = str(digest) if digest else None

    async def judge(self, topic: TopicView, document: DocumentView) -> Verdict:
        messages = build_prompt(topic, document)
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": 160,
            "response_format": {"type": "json_object"},
        }

        started = time.perf_counter()
        last_error = "no attempt made"
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = await self.client.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last_error = f"transport: {exc}"
                await self._backoff(attempt)
                continue

            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                await self._backoff(attempt)
                continue
            if response.status_code >= 400:
                raise AssessorError(
                    f"LLM endpoint rejected the request: HTTP {response.status_code} "
                    f"{response.text[:300]}"
                )

            text = _completion_text(response.json())
            parsed = parse_grade(text)
            if parsed is None:
                last_error = f"unparseable answer: {text[:200]!r}"
                log.warning("assessor_unparseable", attempt=attempt, answer=text[:200])
                await self._backoff(attempt)
                continue

            grade, reason = parsed
            return Verdict(
                grade=grade,
                reason=reason,
                raw=text,
                seconds=time.perf_counter() - started,
                attempts=attempt,
            )

        raise AssessorError(
            f"no usable grade after {self.config.max_retries} attempts ({last_error})"
        )

    @staticmethod
    async def _backoff(attempt: int) -> None:
        await asyncio.sleep(min(2 ** (attempt - 1), 8))


def _completion_text(payload: Any) -> str:
    try:
        choices = payload["choices"]
        message = choices[0]["message"]
        content = message.get("content") or ""
        return str(content)
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _host_only(url: str) -> str:
    match = re.match(r"^(\w+://[^/]+)", url)
    return match.group(1) if match else url
