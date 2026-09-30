"""Search endpoints — the document-selection module's public surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from irs.api.schemas import (
    RankerOut,
    ScoreExplanationOut,
    SearchRequest,
    SearchResponseOut,
)
from irs.db.session import get_session
from irs.logging import get_logger
from irs.selection import service
from irs.selection.base import SearchFilters
from irs.selection.explain import explain_score
from irs.selection.parser import parse_query
from irs.selection.registry import describe_rankers, ranker_info_dict

log = get_logger("irs.api.search")
router = APIRouter(prefix="/search", tags=["search"])


@router.get("/rankers", response_model=list[RankerOut], summary="Available rankers")
async def list_rankers() -> list[RankerOut]:
    """Describe every document-selection strategy.

    The interface renders its ranker selector from this rather than a hard-coded list, so
    a strategy that cannot load (embeddings disabled, for instance) is shown as
    unavailable with its reason instead of failing when selected.
    """
    return [RankerOut(**ranker_info_dict(info)) for info in describe_rankers()]


@router.post("", response_model=SearchResponseOut, summary="Search the collection")
async def run_search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponseOut:
    """Rank the collection against a natural-language query."""
    try:
        response = await service.search(
            session=session,
            raw_query=request.query,
            ranker_key=request.ranker,
            filters=SearchFilters(
                all_words_together=request.all_words_together,
                date_from=request.date_from,
                date_to=request.date_to,
                source_domain=request.source_domain,
            ),
            limit=request.limit,
            offset=request.offset,
        )
    except LookupError as exc:
        # An unavailable ranker is a client error, not a server fault.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return SearchResponseOut.model_validate(response, from_attributes=True)


@router.get(
    "/explain/{document_id}",
    response_model=ScoreExplanationOut,
    summary="Why did this document rank here?",
)
async def explain(
    document_id: int,
    query: str = Query(min_length=1, max_length=512),
    session: AsyncSession = Depends(get_session),
) -> ScoreExplanationOut:
    """Derive one document's similarity score in full.

    Returns every intermediate value — the raw counts, both weights per term, the scalar
    product accumulated term by term, both Euclidean norms and the final cosine — so the
    number in the result list can be checked by hand against the assignment's formulas.
    """
    parsed = await parse_query(session, query)
    explanation = await explain_score(session, document_id, parsed)

    if explanation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"document {document_id} does not exist",
        )

    return ScoreExplanationOut.model_validate(explanation, from_attributes=True)
