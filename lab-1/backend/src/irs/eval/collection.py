"""Test-collection construction.

Evaluating retrieval needs queries paired with relevance judgments, and judgments are
the expensive part. Two complementary strategies are provided, because each answers a
question the other cannot.

**Known-item queries (automatic).** For a sampled document, a query is derived from its
opening sentences and the source document is the one relevant answer. Judgments are
therefore exact, reproducible and — crucially — produced *without reference to any
ranker's output*, so they carry none of the pool bias that a small pooled collection
suffers from. Two design decisions keep this honest:

* Words occurring in the document's **title are removed** from the query. Otherwise the
  task degenerates into exact title matching, which trivially favours lexical rankers and
  measures nothing interesting.
* Query terms are taken in **document order**, not selected by inverse document
  frequency. Choosing the terms our own IDF considers distinctive would tilt the
  comparison toward the TF-IDF ranker by construction.

Its limitation is real and stated in the report: `R = 1` per query, so recall and the
interpolated curve degenerate, and a description drawn from the document's own prose
still shares its vocabulary. It measures known-item finding, not topical retrieval.

**Topical queries (human-judged).** Hand-authored topics judged through the interface
over a pool built from every ranker's output plus two non-system sources. This is the
methodology ROMIP itself used and the primary evidence for the report; it requires a
human assessor, which is why the automatic set exists alongside it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Document, Judgment, Posting, Query, Term, TestCollection
from irs.db.models.enums import AssessorKind, PoolSource, RelevanceGrade
from irs.db.models.evaluation import Assessor, PoolEntry
from irs.logging import get_logger
from irs.nlp.pipeline import analyzer

log = get_logger("irs.eval.collection")

#: Name of the automatically-built collection.
KNOWN_ITEM_COLLECTION = "known-item (automatic)"

#: The synthetic assessor credited with automatic judgments, so they are never confused
#: with a human's and can be filtered out of agreement statistics.
AUTO_ASSESSOR = "automatic (known-item)"

#: Content words per generated query. Long enough to identify one document among a few
#: hundred, short enough to resemble something a person would type.
QUERY_TERMS = 7

#: Characters of the document's opening used as the query's source.
LEAD_CHARS = 600

#: A document needs at least this much text to make a usable known-item topic.
MIN_TEXT_CHARS = 1_200


@dataclass(slots=True)
class GeneratedTopic:
    document_id: int
    title: str
    query: str
    terms: list[str]


async def build_known_item_collection(
    session: AsyncSession,
    size: int = 30,
    seed: int | None = None,
    replace: bool = False,
) -> tuple[TestCollection, list[GeneratedTopic]]:
    """Generate a known-item test collection from the indexed documents.

    Args:
        session: database session.
        size: how many topics to generate.
        seed: RNG seed. Fixed by default so the collection is reproducible — a test
            collection that changes between runs makes its metrics uncomparable.
        replace: drop an existing collection of the same name first.

    Returns:
        The collection and the topics generated for it.
    """
    from irs.config import settings

    rng = random.Random(settings.evaluation.random_seed if seed is None else seed)

    existing = (
        await session.execute(
            select(TestCollection).where(TestCollection.name == KNOWN_ITEM_COLLECTION)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if not replace:
            topics = await _describe_existing(session, existing)
            log.info(
                "known_item_collection_exists",
                collection_id=existing.id,
                queries=len(topics),
            )
            return existing, topics
        await session.delete(existing)
        await session.flush()

    collection = TestCollection(
        name=KNOWN_ITEM_COLLECTION,
        description=(
            "Automatically generated known-item topics. Each query is derived from a "
            "document's opening sentences with its title words removed; that document is "
            "the single relevant answer. Judgments are exact and independent of any "
            "ranker's output, so the set carries no pool bias — but R = 1 per topic, and "
            "the query shares the document's vocabulary, so it measures known-item "
            "finding rather than topical retrieval."
        ),
        frozen_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(collection)
    await session.flush()

    assessor = await _get_or_create_assessor(session, AUTO_ASSESSOR)

    # Ordered by id, then materialised into a list so it can be shuffled: a fixed seed
    # must always shuffle the same starting sequence for the collection to be reproducible.
    candidates = list(
        (
            await session.execute(
                select(Document.id, Document.title, Document.text)
                .where(func.length(Document.text) >= MIN_TEXT_CHARS)
                .order_by(Document.id)
            )
        ).all()
    )

    if not candidates:
        log.warning("known_item_no_candidates", min_chars=MIN_TEXT_CHARS)
        return collection, []

    rng.shuffle(candidates)

    # Terms present in the dictionary; a query term absent from the index could never be
    # matched by any ranker and would silently make the topic unanswerable.
    known_terms = {row[0] for row in (await session.execute(select(Term.lemma))).all()}

    generated: list[GeneratedTopic] = []
    for row in candidates:
        if len(generated) >= size:
            break
        topic = _derive_topic(row.id, row.title, row.text, known_terms)
        if topic is not None:
            generated.append(topic)

    for index, topic in enumerate(generated, start=1):
        query = Query(
            collection_id=collection.id,
            ext_id=index,
            title=topic.query,
            description=f"Find the document this description was taken from: {topic.title}",
            narrative=(
                "Relevant only if this is the source document. Derived automatically, "
                "so exactly one document is relevant."
            ),
            category="known-item",
            is_judged=True,
            selected_at=datetime.now(UTC).replace(tzinfo=None),
        )
        session.add(query)
        await session.flush()

        # The source document is the vital answer, recorded as a judgment by the
        # synthetic assessor so it flows through the same OR/AND aggregation as a human's.
        session.add(
            Judgment(
                query_id=query.id,
                document_id=topic.document_id,
                assessor_id=assessor.id,
                grade=RelevanceGrade.VITAL,
            )
        )
        session.add(
            PoolEntry(
                query_id=query.id,
                document_id=topic.document_id,
                source=PoolSource.MANUAL_SEED,
                pool_depth=None,
                contributed_by={"origin": "known-item generator"},
            )
        )

    await session.flush()
    log.info(
        "known_item_collection_built",
        collection_id=collection.id,
        queries=len(generated),
        seed=settings.evaluation.random_seed if seed is None else seed,
    )
    return collection, generated


def _derive_topic(
    document_id: str | int, title: str, text: str, known_terms: set[str]
) -> GeneratedTopic | None:
    """Build one known-item query from a document's opening.

    Returns ``None`` when the document yields too few usable terms — a stub article or
    one whose lead is mostly proper nouns already in the title.
    """
    lead = (text or "")[:LEAD_CHARS]
    if not lead.strip():
        return None

    image = analyzer.analyze(lead)
    title_image = analyzer.analyze(title or "")
    title_lemmas = set(title_image.terms)

    # Document order, not IDF order: selecting the terms our own weighting considers
    # distinctive would bias the comparison toward the TF-IDF ranker.
    terms = [
        lemma
        for lemma in image.ordered_lemmas
        if lemma not in title_lemmas and lemma in known_terms
    ][:QUERY_TERMS]

    if len(terms) < 4:
        return None

    return GeneratedTopic(
        document_id=int(document_id),
        title=title or "",
        query=" ".join(terms),
        terms=terms,
    )


async def _describe_existing(
    session: AsyncSession, collection: TestCollection
) -> list[GeneratedTopic]:
    rows = (
        await session.execute(
            select(Query.id, Query.title, Query.description, Judgment.document_id)
            .join(Judgment, Judgment.query_id == Query.id)
            .where(Query.collection_id == collection.id)
            .order_by(Query.ext_id)
        )
    ).all()
    return [
        GeneratedTopic(
            document_id=row.document_id,
            title=(row.description or "").split(": ", 1)[-1],
            query=row.title,
            terms=row.title.split(),
        )
        for row in rows
    ]


async def _get_or_create_assessor(session: AsyncSession, name: str) -> Assessor:
    assessor = (
        await session.execute(select(Assessor).where(Assessor.name == name))
    ).scalar_one_or_none()
    if assessor is None:
        assessor = Assessor(
            name=name,
            kind=AssessorKind.AUTOMATIC,
            note=(
                "Synthetic assessor for automatically-derived judgments. Excluded from "
                "inter-assessor agreement, which is only meaningful between humans."
            ),
        )
        session.add(assessor)
        await session.flush()
    return assessor


async def collection_summary(session: AsyncSession, collection_id: int) -> dict[str, int]:
    """Counts describing a collection, for the interface and the report."""
    queries = int(
        (
            await session.execute(
                select(func.count()).select_from(Query).where(Query.collection_id == collection_id)
            )
        ).scalar_one()
    )
    judged = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Query)
                .where(Query.collection_id == collection_id, Query.is_judged)
            )
        ).scalar_one()
    )
    judgments = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Judgment)
                .join(Query, Query.id == Judgment.query_id)
                .where(Query.collection_id == collection_id)
            )
        ).scalar_one()
    )
    pooled = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PoolEntry)
                .join(Query, Query.id == PoolEntry.query_id)
                .where(Query.collection_id == collection_id)
            )
        ).scalar_one()
    )
    return {
        "queries": queries,
        "judged_queries": judged,
        "judgments": judgments,
        "pool_entries": pooled,
    }


async def documents_available(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(Document))).scalar_one())


async def has_postings(session: AsyncSession) -> bool:
    """Whether the index has been built — nothing can be evaluated without it."""
    return bool((await session.execute(select(Posting.term_id).limit(1))).scalar_one_or_none())
