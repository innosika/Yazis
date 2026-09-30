"""Shared filter predicates.

The assignment's ``Search`` class defines ``dateStartString``/``dateEndString`` and a
source restriction that apply regardless of which ranker is selected. Building them once
here means every ranker filters identically — otherwise a comparison between two rankers
would partly be a comparison of their filtering, which would invalidate the evaluation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Date, cast, func

from irs.db.models import Document
from irs.selection.base import SearchFilters


def apply_document_filters(filters: SearchFilters) -> list[Any]:
    """Build the document-level WHERE conditions for a search.

    Date bounds test ``published_at`` and fall back to ``fetched_at`` for pages that
    declare no date of their own — without the fallback, every undated page would
    silently disappear as soon as a user set any date filter, which looks like a bug in
    retrieval rather than a consequence of missing metadata.
    """
    conditions: list[Any] = []

    effective_date = func.coalesce(Document.published_at, cast(Document.fetched_at, Date))

    if filters.date_from is not None:
        conditions.append(effective_date >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(effective_date <= filters.date_to)
    if filters.source_domain:
        conditions.append(Document.source_domain == filters.source_domain)

    return conditions
