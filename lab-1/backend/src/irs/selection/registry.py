"""Ranker registry.

One place that knows which document-selection strategies exist, so the API, the
evaluation runner and the UI's ranker selector all agree without any of them hard-coding
a list. Rankers whose dependencies are unavailable (embeddings disabled, model missing)
are simply absent rather than present-but-broken.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from irs.config import settings
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import Ranker

log = get_logger("irs.selection.registry")


@dataclass(frozen=True, slots=True)
class RankerInfo:
    """Presentation metadata, so the UI renders itself from the registry."""

    key: RankerKey
    label: str
    description: str
    #: True for the strategy the assignment mandates for variant 34.
    is_required_model: bool = False
    available: bool = True
    unavailable_reason: str | None = None


_INFO: dict[RankerKey, RankerInfo] = {
    RankerKey.VECTOR: RankerInfo(
        key=RankerKey.VECTOR,
        label="Vector model",
        description=(
            "TF-IDF term weights with cosine similarity. The retrieval strategy this "
            "assignment specifies for variant 34, implemented directly from its formulas."
        ),
        is_required_model=True,
    ),
    RankerKey.BM25: RankerInfo(
        key=RankerKey.BM25,
        label="BM25",
        description=(
            "Probabilistic ranking with saturating term frequency and length "
            "normalisation. The standard baseline the vector model is measured against."
        ),
    ),
    RankerKey.FTS: RankerInfo(
        key=RankerKey.FTS,
        label="PostgreSQL full-text",
        description=(
            "The database's own tsvector index and ts_rank. Included as an external "
            "reference point that shares none of our indexing code."
        ),
    ),
    RankerKey.SEMANTIC: RankerInfo(
        key=RankerKey.SEMANTIC,
        label="Semantic",
        description=(
            "Dense sentence embeddings compared by cosine distance in pgvector. Matches "
            "meaning rather than vocabulary, so it answers paraphrased queries the "
            "lexical rankers miss."
        ),
    ),
    RankerKey.HYBRID: RankerInfo(
        key=RankerKey.HYBRID,
        label="Hybrid",
        description=(
            "Reciprocal-rank fusion of the vector, BM25 and semantic rankings. Combines "
            "lexical precision with semantic recall."
        ),
    ),
    RankerKey.VECTOR_IDF: RankerInfo(
        key=RankerKey.VECTOR_IDF,
        label="Vector · IDF query",
        description=(
            "The mandated vector model with one change: query words are weighted by "
            "their inverse document frequency instead of being binary. An improvement "
            "proposal measured against the mandated model rather than asserted."
        ),
    ),
    RankerKey.VECTOR_PRF: RankerInfo(
        key=RankerKey.VECTOR_PRF,
        label="Vector · Rocchio PRF",
        description=(
            "The mandated vector model followed by one round of Rocchio pseudo-relevance "
            "feedback: the top documents of the first pass expand the query, which is "
            "scored again. The selection module's learning step, measured in the arena."
        ),
    ),
}


def _load() -> dict[RankerKey, Ranker]:
    """Import and instantiate every available ranker.

    Imports are local and individually guarded: a ranker that cannot load (for example
    the semantic one when the embedding model is absent) must not prevent the rest of the
    system from serving searches.
    """
    rankers: dict[RankerKey, Ranker] = {}

    from irs.selection.vector import ranker as vector_ranker

    rankers[RankerKey.VECTOR] = vector_ranker

    for key, module_path, attribute in (
        (RankerKey.BM25, "irs.selection.bm25", "ranker"),
        (RankerKey.FTS, "irs.selection.fts", "ranker"),
        (RankerKey.SEMANTIC, "irs.selection.semantic", "ranker"),
        (RankerKey.HYBRID, "irs.selection.hybrid", "ranker"),
        (RankerKey.VECTOR_IDF, "irs.selection.vector_idf", "ranker"),
        (RankerKey.VECTOR_PRF, "irs.selection.vector_prf", "ranker"),
    ):
        if key is RankerKey.SEMANTIC and not settings.semantic.enabled:
            _INFO[key] = replace(
                _INFO[key],
                available=False,
                unavailable_reason="embeddings are disabled (SEMANTIC_ENABLED=false)",
            )
            continue
        try:
            module = __import__(module_path, fromlist=[attribute])
            rankers[key] = getattr(module, attribute)
        except Exception as exc:
            _INFO[key] = replace(
                _INFO[key],
                available=False,
                unavailable_reason=f"{type(exc).__name__}: {exc}"[:160],
            )
            log.debug("ranker_unavailable", ranker=key, error=str(exc))

    return rankers


_rankers: dict[RankerKey, Ranker] | None = None


def get_rankers() -> dict[RankerKey, Ranker]:
    global _rankers
    if _rankers is None:
        _rankers = _load()
        log.info("rankers_loaded", available=sorted(str(k) for k in _rankers))
    return _rankers


def get_ranker(key: RankerKey) -> Ranker:
    rankers = get_rankers()
    if key not in rankers:
        info = _INFO.get(key)
        reason = info.unavailable_reason if info else "unknown ranker"
        raise LookupError(f"ranker {key!r} is not available: {reason}")
    return rankers[key]


def describe_rankers() -> list[RankerInfo]:
    """Registry metadata for the UI, required model first."""
    available = set(get_rankers())
    described = [
        replace(info, available=info.key in available and info.available) for info in _INFO.values()
    ]
    return sorted(described, key=lambda i: (not i.is_required_model, not i.available, i.key))


def ranker_info_dict(info: RankerInfo) -> dict[str, object]:
    """Plain dict form, for serialisation. `slots=True` means no ``__dict__``."""
    return asdict(info)
