"""Contracts for the document-selection module.

Variant 34 designates «модуль отбора документов» as the component carrying the
assignment's intelligence, so it is structured as a family of interchangeable rankers
behind one interface. The vector model is the one the variant mandates; the others exist
so the evaluation module can show it was measured against alternatives rather than
assumed adequate.

The interface is deliberately narrow — a ranker receives a parsed query and returns
scored document ids. Snippet construction, highlighting and score explanation are
separate concerns handled once, for every ranker, rather than reimplemented in each.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from irs.db.models.enums import RankerKey


@dataclass(slots=True)
class SearchFilters:
    """Post-retrieval restrictions.

    These mirror the fields on the assignment's ``Search`` class: ``allWordsTogether``,
    ``dateStartString`` and ``dateEndString``.
    """

    #: Require every query term to occur in the document — the assignment's
    #: `allWordsTogether`. Turns the ranked vector query into a conjunctive one, which
    #: raises precision and lowers recall.
    all_words_together: bool = False
    #: Inclusive publication-date bounds.
    date_from: date | None = None
    date_to: date | None = None
    #: Restrict to one source host. Useful when the crawl spans several sites.
    source_domain: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.all_words_together or self.date_from or self.date_to or self.source_domain)


@dataclass(slots=True)
class ParsedQuery:
    """A query's search image (поисковый образ запроса).

    Produced once per search and shared by every ranker, so that a comparison between
    rankers cannot be contaminated by differences in query analysis.
    """

    #: What the user typed.
    raw: str
    #: Distinct lemmas, in the order they first appeared. Order is preserved so the
    #: "words of your query found in this document" list reads in the user's own order.
    lemmas: list[str] = field(default_factory=list)
    #: Dictionary ids of those lemmas that exist in the index. A query term absent from
    #: the dictionary cannot match anything and is reported separately.
    term_ids: dict[str, int] = field(default_factory=dict)
    #: `B_i` per known lemma.
    inverse_frequencies: dict[str, float] = field(default_factory=dict)
    #: `N_k` per known lemma. Needed by the score explanation to report a query term's
    #: document frequency even for documents that do not contain it.
    document_frequencies: dict[str, int] = field(default_factory=dict)
    #: Query lemmas that are not in the dictionary at all.
    unknown_lemmas: list[str] = field(default_factory=list)
    #: Surface forms the user typed, per lemma, for highlighting what they actually wrote.
    surface_forms: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_answerable(self) -> bool:
        """False when no query term exists in the dictionary — nothing can match."""
        return bool(self.term_ids)

    @property
    def known_lemmas(self) -> list[str]:
        return [lemma for lemma in self.lemmas if lemma in self.term_ids]


@dataclass(slots=True)
class ScoredDocument:
    """A document id with its score, before presentation details are attached."""

    document_id: int
    score: float
    #: Query lemmas this document contains. Feeds the assignment's requirement that
    #: results show «список слов запроса присутствующих в документе».
    matched_lemmas: list[str] = field(default_factory=list)
    #: Ranker-specific detail: the dot product, the BM25 sum, the fusion contributions.
    detail: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RankedPage:
    """A ranker's answer: the requested window, plus how much matched in total.

    The distinction matters for the interface and for the report. ``documents`` is the
    page the user asked for, while ``total_candidates`` is how many documents the ranker
    considered relevant at all — the size of the search output («поисковая выдача»).
    Reporting the length of the page as the candidate count would make every query look
    as though it matched exactly as many documents as were displayed.
    """

    documents: list[ScoredDocument] = field(default_factory=list)
    total_candidates: int = 0

    def __len__(self) -> int:
        return len(self.documents)


class Ranker(Protocol):
    """A document-selection strategy."""

    key: RankerKey
    label: str

    async def rank(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        filters: SearchFilters,
        limit: int,
    ) -> RankedPage:
        """Return up to ``limit`` documents, best first, with the total match count.

        Implementations must break ties deterministically (by ascending document id), so
        that repeating a run reproduces the same ranking. TF-IDF cosine in particular
        produces exact ties whenever two documents share the same query-term weights,
        and a nondeterministic order there would make evaluation metrics flicker between
        otherwise identical runs.
        """
        ...
