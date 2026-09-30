"""Semantic ranker — dense embeddings compared in pgvector.

Where the vector model matches *words*, this matches *meaning*: a query and a document
that share no vocabulary can still be close if they express the same idea. That is the
synonymy problem the assignment's own theory section raises when it introduces latent
semantic analysis, addressed with a modern encoder instead of a matrix factorisation.

Its presence in the arena is what makes the evaluation informative. A collection of
queries phrased in the documents' own vocabulary cannot distinguish these rankers at all;
paraphrased queries separate them sharply, which is why the test collection deliberately
includes vocabulary-mismatch topics.

Retrieval uses an HNSW index over cosine distance, so the scan is approximate rather than
exhaustive. Similarity is reported as ``1 − distance`` to put it on the same 0–1 scale as
the other rankers.
"""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Document, Posting, Term
from irs.db.models.enums import RankerKey
from irs.logging import get_logger
from irs.nlp.embeddings import embedder
from irs.selection.base import ParsedQuery, RankedPage, ScoredDocument, SearchFilters
from irs.selection.filters import apply_document_filters

log = get_logger("irs.selection.semantic")


class SemanticRanker:
    """Cosine similarity over dense embeddings."""

    key = RankerKey.SEMANTIC
    label = "Semantic (embeddings)"

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        raw = (query.raw or "").strip()
        if not raw:
            return RankedPage()

        # The encoder is given the user's original text, not the lemmatised search image:
        # it was trained on natural language, and stripping function words and inflection
        # removes exactly the signal a sentence encoder uses.
        vector = await embedder.embed_one(raw)
        if vector is None:
            return RankedPage()

        distance = Document.embedding.cosine_distance(vector)
        similarity = (1.0 - distance).label("score")

        statement = select(Document.id.label("document_id"), similarity).where(
            Document.embedding.isnot(None)
        )

        conditions = apply_document_filters(filters)
        if conditions:
            statement = statement.where(and_(*conditions))

        if filters.all_words_together and query.term_ids:
            # `allWordsTogether` is a lexical condition, so it restricts the semantic
            # ordering rather than being silently ignored: the documents are still ranked
            # by meaning, but only those containing every query term are eligible.
            statement = statement.where(Document.id.in_(_documents_containing_all(query)))

        candidates = statement
        statement = statement.order_by(distance.asc(), Document.id.asc()).limit(limit)

        # A dense ranker applies no lexical cut, so every embedded document that passes
        # the filters is a candidate; this reports that eligible set.
        total_candidates = int(
            (
                await session.execute(select(func.count()).select_from(candidates.subquery()))
            ).scalar_one()
        )
        rows = (await session.execute(statement)).all()

        results = [
            ScoredDocument(
                document_id=row.document_id,
                score=float(row.score),
                matched_lemmas=[],
                detail={"cosine_similarity": float(row.score)},
            )
            for row in rows
        ]

        if results:
            await self._attach_matches(session, query, results)

        log.info(
            "semantic_ranked",
            raw=raw[:120],
            results=len(results),
            top_score=round(results[0].score, 6) if results else 0.0,
            model=embedder.model_name,
            candidates=total_candidates,
        )
        return RankedPage(documents=results, total_candidates=total_candidates)

    async def _attach_matches(
        self, session: AsyncSession, query: ParsedQuery, results: list[ScoredDocument]
    ) -> None:
        """Report which query words each result contains.

        A semantic match may well contain none of them — which is the interesting case,
        and showing an empty list makes that visible rather than confusing.
        """
        if not query.term_ids:
            return

        rows = (
            await session.execute(
                select(Posting.document_id, Term.lemma)
                .join(Term, Term.id == Posting.term_id)
                .where(
                    Posting.document_id.in_([r.document_id for r in results]),
                    Posting.term_id.in_(list(query.term_ids.values())),
                )
            )
        ).all()

        by_document: dict[int, set[str]] = {}
        for document_id, lemma in rows:
            by_document.setdefault(document_id, set()).add(lemma)

        for result in results:
            found = by_document.get(result.document_id, set())
            result.matched_lemmas = [lemma for lemma in query.lemmas if lemma in found]


ranker = SemanticRanker()


def _documents_containing_all(query: ParsedQuery):  # type: ignore[no-untyped-def]
    """Subquery selecting documents that contain every known query term."""
    return (
        select(Posting.document_id)
        .where(Posting.term_id.in_(list(query.term_ids.values())))
        .group_by(Posting.document_id)
        .having(func.count(func.distinct(Posting.term_id)) == len(query.term_ids))
    )
