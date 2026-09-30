"""Query parsing: natural-language text → :class:`ParsedQuery`.

Runs the *same* linguistic pipeline as document indexing, which the assignment requires:
a query's search image and a document's must share one structure within a single system,
otherwise the two vectors would not be indexed by the same dictionary.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models import Term
from irs.logging import get_logger
from irs.nlp.pipeline import analyzer
from irs.selection.base import ParsedQuery

log = get_logger("irs.selection.parser")


async def parse_query(session: AsyncSession, raw: str) -> ParsedQuery:
    """Analyse a query and resolve its terms against the dictionary.

    Query terms missing from the dictionary are kept in
    :attr:`ParsedQuery.unknown_lemmas` rather than silently dropped: telling the user
    that a word of their query appears nowhere in the collection explains an empty or
    surprising result set far better than returning nothing without comment.
    """
    # Off the event loop: see the note in irs.index.builder.
    image = await asyncio.to_thread(analyzer.analyze_query, raw)
    lemmas = image.ordered_lemmas

    if not lemmas:
        log.info("query_parsed_empty", raw=raw[:120])
        return ParsedQuery(raw=raw)

    rows = (
        await session.execute(
            select(Term.id, Term.lemma, Term.idf, Term.document_frequency).where(
                Term.lemma.in_(lemmas)
            )
        )
    ).all()

    term_ids = {row.lemma: row.id for row in rows}
    inverse_frequencies = {row.lemma: row.idf for row in rows}
    document_frequencies = {row.lemma: row.document_frequency for row in rows}
    unknown = [lemma for lemma in lemmas if lemma not in term_ids]

    parsed = ParsedQuery(
        raw=raw,
        lemmas=lemmas,
        term_ids=term_ids,
        inverse_frequencies=inverse_frequencies,
        document_frequencies=document_frequencies,
        unknown_lemmas=unknown,
    )

    log.info(
        "query_parsed",
        raw=raw[:120],
        lemmas=lemmas,
        known=len(term_ids),
        unknown=unknown,
    )
    return parsed
