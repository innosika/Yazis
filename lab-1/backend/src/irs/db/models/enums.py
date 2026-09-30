"""Enumerations shared by the models and the API schemas."""

from __future__ import annotations

from enum import StrEnum


class RankerKey(StrEnum):
    """The document-selection strategies (the variant-34 «модуль отбора документов»).

    ``VECTOR`` is the model the assignment mandates; the rest exist so the evaluation
    module can demonstrate that the chosen model was measured against alternatives
    rather than asserted to be good.
    """

    VECTOR = "vector"  # TF-IDF weights + cosine similarity — the required model
    BM25 = "bm25"  # Okapi BM25 probabilistic baseline
    FTS = "fts"  # PostgreSQL tsvector / ts_rank baseline
    SEMANTIC = "semantic"  # dense embeddings, cosine over pgvector
    HYBRID = "hybrid"  # reciprocal-rank fusion of vector + bm25 + semantic
    #: Improvement proposals, measured against the mandated model rather than asserted:
    #: the same TF-IDF document vectors, but the query weighted by IDF instead of binary…
    VECTOR_IDF = "vector_idf"
    #: …and the binary query expanded by Rocchio pseudo-relevance feedback.
    VECTOR_PRF = "vector_prf"


class AssessorKind(StrEnum):
    """Who — or what — produced a judgment.

    Agreement statistics are only meaningful between independent humans, and an LLM's
    verdicts must never be presented as a person's, so the kind is stored explicitly
    rather than inferred from the assessor's name.
    """

    HUMAN = "human"
    #: The synthetic known-item assessor: judgments follow from the construction.
    AUTOMATIC = "automatic"
    #: A language model prompted with the topic and the document.
    LLM = "llm"


class RelevanceGrade(StrEnum):
    """ROMIP's five-point assessment scale.

    ROMIP moved off a binary judgment deliberately — forcing assessors to choose
    black or white makes them over-critical («деление на "черное"/"белое" ставит перед
    асессором психологическую проблему»). Grades are collected on this scale and
    collapsed to binary only at scoring time.
    """

    VITAL = "VITAL"  # соответствующий (релевантный/витальный)
    RELEVANT_PLUS = "RELEVANT_PLUS"  # скорее соответствующий
    RELEVANT_MINUS = "RELEVANT_MINUS"  # возможно соответствующий
    NOTRELEVANT = "NOTRELEVANT"  # не соответствующий
    CANTBEJUDGED = "CANTBEJUDGED"  # документ не может быть оценен


#: Numeric gain per grade. ``CANTBEJUDGED`` scores 0 like an explicit non-match, but is
#: tracked separately because it means "no opinion", which the OR/AND aggregation treats
#: differently from a negative judgment.
GRADE_VALUES: dict[RelevanceGrade, int] = {
    RelevanceGrade.VITAL: 3,
    RelevanceGrade.RELEVANT_PLUS: 2,
    RelevanceGrade.RELEVANT_MINUS: 1,
    RelevanceGrade.NOTRELEVANT: 0,
    RelevanceGrade.CANTBEJUDGED: 0,
}


class QrelAggregation(StrEnum):
    """How multiple assessors' grades combine into one binary judgment.

    ROMIP publishes both, and reports that the ranker ordering was not always stable
    between them — which is why we materialise both rather than picking one.
    """

    #: слабые требования — relevant if *any* assessor exceeded the threshold.
    OR = "or"
    #: сильные требования — non-relevant if *any* assessor fell below it.
    AND = "and"


class PoolSource(StrEnum):
    """Provenance of a judged query-document pair.

    Recorded so the report can *prove* the judgments were not confined to what our own
    rankers returned — the pool bias a small evaluation is most open to criticism for.
    """

    RUN_UNION = "run_union"  # union of the rankers' top-k
    ORACLE = "oracle"  # hand-built synonym/keyword run
    RANDOM_SAMPLE = "random_sample"  # unjudged documents from outside the pool
    MANUAL_SEED = "manual_seed"  # added by hand while authoring the topic


class CrawlStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UrlStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FETCHED = "fetched"
    INDEXED = "indexed"
    SKIPPED = "skipped"
    FAILED = "failed"


class SkipReason(StrEnum):
    """Why a URL was not indexed. Surfaced in the crawl UI and the report."""

    ROBOTS_DISALLOWED = "robots_disallowed"
    WRONG_CONTENT_TYPE = "wrong_content_type"
    TOO_LARGE = "too_large"
    TOO_SHORT = "too_short"
    DUPLICATE_URL = "duplicate_url"
    DUPLICATE_CONTENT = "duplicate_content"
    NEAR_DUPLICATE = "near_duplicate"
    EXTRACTION_FAILED = "extraction_failed"
    WRONG_LANGUAGE = "wrong_language"
    DEPTH_EXCEEDED = "depth_exceeded"
    OFF_DOMAIN = "off_domain"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"


class EvalRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SignificanceTest(StrEnum):
    PERMUTATION = "permutation"
    WILCOXON = "wilcoxon"
    TTEST_REL = "ttest_rel"
