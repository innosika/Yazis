"""Hybrid ranker — reciprocal rank fusion of the lexical and semantic rankings.

Lexical retrieval and dense retrieval fail in different ways. TF-IDF cannot match a
paraphrase; an encoder can miss an exact rare term such as a product code or a surname.
Fusing them recovers most of each one's strengths.

Fusion is by **reciprocal rank** rather than by combining scores:

    RRF(d) = Σ_r  1 / (k + rank_r(d))

Scores are deliberately not summed. A cosine over TF-IDF weights, a BM25 sum and an
embedding similarity live on incomparable scales — BM25 is unbounded above while the
other two are bounded by 1 — so any weighted sum of them is dominated by whichever
happens to have the largest spread on that query, not by whichever is most reliable.
Ranks are scale-free, so RRF needs no per-ranker calibration and no tuning beyond `k`,
whose usual value of 60 damps the influence of the very top positions just enough that a
single ranker cannot dictate the fused order alone.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.selection.base import (
    ParsedQuery,
    RankedPage,
    Ranker,
    ScoredDocument,
    SearchFilters,
)

log = get_logger("irs.selection.hybrid")

#: Rankers fused, in the order their contributions are reported.
_COMPONENTS: tuple[RankerKey, ...] = (
    RankerKey.VECTOR,
    RankerKey.BM25,
    RankerKey.SEMANTIC,
)

#: How deep each component contributes. Deeper than the requested limit, because a
#: document ranked 40th by one ranker and 3rd by another should still surface.
_COMPONENT_DEPTH = 60


@dataclass(slots=True)
class _Contribution:
    ranker: RankerKey
    rank: int
    score: float


class HybridRanker:
    """Reciprocal rank fusion over the available component rankers."""

    key = RankerKey.HYBRID
    label = "Hybrid (RRF)"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        components = self._components()
        if not components:
            return RankedPage()

        # Components run concurrently. They are independent reads, and the semantic one
        # pays for model inference, so serialising them would make the hybrid ranker
        # roughly as slow as the sum of its parts.
        rankings = await asyncio.gather(
            *(
                component.rank(session, query, filters, _COMPONENT_DEPTH)
                for _, component in components
            ),
            return_exceptions=True,
        )

        k = settings.search.rrf_k
        fused: dict[int, float] = {}
        contributions: dict[int, list[_Contribution]] = {}
        matched: dict[int, list[str]] = {}
        used: list[str] = []

        for (key, _), ranking in zip(components, rankings, strict=True):
            if isinstance(ranking, BaseException):
                # One failing component must not fail the fusion; it simply does not vote.
                log.warning("hybrid_component_failed", component=str(key), error=str(ranking))
                continue

            used.append(str(key))
            for position, result in enumerate(ranking.documents, start=1):
                fused[result.document_id] = fused.get(result.document_id, 0.0) + 1.0 / (
                    k + position
                )
                contributions.setdefault(result.document_id, []).append(
                    _Contribution(ranker=key, rank=position, score=result.score)
                )
                # Keep the richest matched-term list any component produced: the lexical
                # rankers know the terms, the semantic one does not.
                if result.matched_lemmas and len(result.matched_lemmas) > len(
                    matched.get(result.document_id, [])
                ):
                    matched[result.document_id] = result.matched_lemmas

        if not fused:
            return RankedPage()

        ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:limit]

        results = [
            ScoredDocument(
                document_id=document_id,
                score=score,
                matched_lemmas=matched.get(document_id, []),
                detail={
                    "rrf_k": float(k),
                    "components": float(len(contributions.get(document_id, []))),
                    **{
                        f"rank_{contribution.ranker}": float(contribution.rank)
                        for contribution in contributions.get(document_id, [])
                    },
                },
            )
            for document_id, score in ordered
        ]

        log.info(
            "hybrid_ranked",
            raw=query.raw[:120],
            components=used,
            candidates=len(fused),
            results=len(results),
            top_score=round(results[0].score, 6) if results else 0.0,
            rrf_k=k,
        )
        # The fused candidate set is the union of the components' candidate sets.
        return RankedPage(documents=results, total_candidates=len(fused))

    @staticmethod
    def _components() -> list[tuple[RankerKey, Ranker]]:
        """The component rankers that are actually available.

        Imported lazily and through the registry, so the hybrid ranker degrades to
        whatever is present — with embeddings disabled it fuses the two lexical rankers
        rather than failing to load.
        """
        from irs.selection.registry import get_rankers

        available = get_rankers()
        return [
            (key, available[key])
            for key in _COMPONENTS
            if key in available and key is not RankerKey.HYBRID
        ]


ranker = HybridRanker()
