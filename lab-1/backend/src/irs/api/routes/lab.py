"""The Relevance Lab: the vector space made visible, and Rocchio feedback made interactive.

``/lab/space`` projects every document — and the query — into the three-dimensional
latent space of the term–document matrix (see :mod:`irs.index.matrix`), so the
assignment's formulas 1.7/1.8 can literally be looked at. ``/lab/feedback`` applies one
Rocchio round to a query from the documents the user marked, returns the new ranking and
the new query position, and appends the round to a replayable session.

One honesty note the interface repeats: the 3-D picture keeps only the fraction of the
geometry the response reports as ``explained_variance_ratio``. The cosine shown for each
document is the *full-space* cosine the ranker actually used, not the angle in the picture.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query as QueryParam
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.config import settings
from irs.db.models import Document, FeedbackSession, LsaProjection, Term
from irs.db.models.enums import RankerKey
from irs.db.session import get_session
from irs.index.builder import get_collection_stat
from irs.index.matrix import build_lsa, load_model, model_basis, project
from irs.logging import get_logger
from irs.selection import rocchio as rocchio_module
from irs.selection.base import SearchFilters
from irs.selection.parser import parse_query
from irs.selection.vector import ranker as vector_ranker

log = get_logger("irs.api.lab")
router = APIRouter(prefix="/lab", tags=["relevance-lab"])


class SpacePointOut(BaseModel):
    document_id: int
    title: str
    url: str
    x: float
    y: float
    z: float
    #: Full-space cosine with the query (0 when the document matches no query term).
    cosine: float = 0.0
    rank: int | None = None


class SpaceQueryOut(BaseModel):
    text: str
    x: float
    y: float
    z: float
    lemmas: list[str] = []
    unknown_lemmas: list[str] = []
    terms_in_basis: int = 0


class SpaceOut(BaseModel):
    index_version: int
    components: int
    explained_variance_ratio: float
    singular_values: list[float]
    document_count: int
    points: list[SpacePointOut]
    query: SpaceQueryOut | None = None
    built_at: datetime | None = None


class LsaBuildIn(BaseModel):
    components: int | None = Field(default=None, ge=1, le=50)


class FeedbackIn(BaseModel):
    session_id: int | None = None
    query: str = Field(min_length=1, max_length=512)
    relevant: list[int] = []
    non_relevant: list[int] = []
    alpha: float | None = Field(default=None, ge=0, le=10)
    beta: float | None = Field(default=None, ge=0, le=10)
    gamma: float | None = Field(default=None, ge=0, le=10)
    limit: int = Field(default=20, ge=1, le=100)


class QueryTermOut(BaseModel):
    term_id: int
    lemma: str
    weight: float
    previous_weight: float | None = None
    is_original: bool = False


class RankingEntryOut(BaseModel):
    rank: int
    document_id: int
    title: str
    url: str
    score: float
    matched_lemmas: list[str] = []
    previous_rank: int | None = None


class IterationOut(BaseModel):
    iteration: int
    relevant: list[int]
    non_relevant: list[int]
    projection: list[float]
    top: list[int]
    term_count: int
    alpha: float
    beta: float
    gamma: float


class FeedbackOut(BaseModel):
    session_id: int
    iteration: int
    original_query: str
    coefficients: dict[str, float]
    query_point: list[float]
    query_terms: list[QueryTermOut]
    added_terms: list[QueryTermOut]
    dropped_terms: list[str]
    ranking: list[RankingEntryOut]
    total_candidates: int
    history: list[IterationOut]
    index_version: int


# ------------------------------------------------------------------ helpers ----


async def _model_for_current_index(session: AsyncSession) -> tuple[Any, int]:
    stat = await get_collection_stat(session)
    model = await load_model(session, stat.index_version)
    if model is None:
        log.info("lsa_model_missing_building", index_version=stat.index_version)
        try:
            await build_lsa(session)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        model = await load_model(session, stat.index_version)
        if model is None:
            raise HTTPException(status_code=500, detail="the projection could not be built")
    return model, stat.index_version


async def _lemmas(session: AsyncSession, term_ids: list[int]) -> dict[int, str]:
    if not term_ids:
        return {}
    rows = (await session.execute(select(Term.id, Term.lemma).where(Term.id.in_(term_ids)))).all()
    return {int(term_id): str(lemma) for term_id, lemma in rows}


def _terms_out(
    vector: dict[int, float],
    lemmas: dict[int, str],
    previous: dict[int, float] | None,
    original: set[int],
) -> list[QueryTermOut]:
    return [
        QueryTermOut(
            term_id=term_id,
            lemma=lemmas.get(term_id, f"#{term_id}"),
            weight=weight,
            previous_weight=previous.get(term_id) if previous is not None else None,
            is_original=term_id in original,
        )
        for term_id, weight in sorted(vector.items(), key=lambda item: (-item[1], item[0]))
    ]


# ------------------------------------------------------------------ endpoints ----


@router.get("/space", response_model=SpaceOut, summary="The projected vector space")
async def space(
    query: str | None = QueryParam(default=None, max_length=512),
    session: AsyncSession = Depends(get_session),
) -> SpaceOut:
    model, index_version = await _model_for_current_index(session)
    basis, column_of_term = model_basis(model)

    rows = (
        await session.execute(
            select(LsaProjection, Document.title, Document.url)
            .join(Document, Document.id == LsaProjection.document_id)
            .where(LsaProjection.index_version == index_version)
            .order_by(LsaProjection.document_id)
        )
    ).all()

    cosines: dict[int, tuple[float, int]] = {}
    query_out: SpaceQueryOut | None = None
    if query:
        parsed = await parse_query(session, query)
        vector = rocchio_module.binary_query_vector(parsed)
        point = project(basis, column_of_term, vector)
        if parsed.is_answerable:
            page = await vector_ranker.rank(session, parsed, SearchFilters(), limit=len(rows) or 1)
            cosines = {
                d.document_id: (d.score, rank) for rank, d in enumerate(page.documents, start=1)
            }
        query_out = SpaceQueryOut(
            text=query,
            x=point[0] if len(point) > 0 else 0.0,
            y=point[1] if len(point) > 1 else 0.0,
            z=point[2] if len(point) > 2 else 0.0,
            lemmas=parsed.lemmas,
            unknown_lemmas=parsed.unknown_lemmas,
            terms_in_basis=sum(1 for t in vector if t in column_of_term),
        )

    points = [
        SpacePointOut(
            document_id=projection.document_id,
            title=title or "(untitled)",
            url=url,
            x=projection.x,
            y=projection.y,
            z=projection.z,
            cosine=cosines.get(projection.document_id, (0.0, None))[0],
            rank=cosines.get(projection.document_id, (0.0, None))[1],
        )
        for projection, title, url in rows
    ]
    return SpaceOut(
        index_version=index_version,
        components=model.components,
        explained_variance_ratio=model.explained_variance_ratio,
        singular_values=list(model.singular_values),
        document_count=len(points),
        points=points,
        query=query_out,
        built_at=model.built_at,
    )


@router.post("/space/build", response_model=dict[str, Any], summary="Rebuild the projection")
async def rebuild_space(
    body: LsaBuildIn | None = None, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    try:
        stats = await build_lsa(session, components=body.components if body else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return stats.as_dict()


@router.post("/feedback", response_model=FeedbackOut, summary="One Rocchio feedback round")
async def feedback(body: FeedbackIn, session: AsyncSession = Depends(get_session)) -> FeedbackOut:
    """Move the query towards the documents marked relevant and away from the others.

    Iteration 0 is the binary query image the assignment specifies. Each round starts
    from the previous round's vector, so the trajectory is cumulative and replayable.
    """
    model, index_version = await _model_for_current_index(session)
    basis, column_of_term = model_basis(model)
    coefficients = {
        "alpha": settings.search.rocchio_alpha if body.alpha is None else body.alpha,
        "beta": settings.search.rocchio_beta if body.beta is None else body.beta,
        "gamma": settings.search.rocchio_gamma if body.gamma is None else body.gamma,
    }

    if body.session_id is not None:
        feedback_session = await session.get(FeedbackSession, body.session_id)
        if feedback_session is None:
            raise HTTPException(
                status_code=404, detail=f"feedback session {body.session_id} not found"
            )
        if feedback_session.index_version != index_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="the index was rebuilt since this session started; start a new session",
            )
    else:
        feedback_session = FeedbackSession(
            original_query=body.query,
            ranker=RankerKey.VECTOR,
            alpha=coefficients["alpha"],
            beta=coefficients["beta"],
            gamma=coefficients["gamma"],
            index_version=index_version,
        )
        session.add(feedback_session)
        await session.flush()

    parsed = await parse_query(session, feedback_session.original_query)
    original = rocchio_module.binary_query_vector(parsed)
    if not original:
        raise HTTPException(status_code=422, detail="no query term exists in the dictionary")

    iterations = list(feedback_session.iterations)
    if iterations:
        previous = {int(k): float(v) for k, v in iterations[-1]["vector"].items()}
    else:
        previous = dict(original)

    marked = await rocchio_module.load_document_vectors(
        session, sorted(set(body.relevant) | set(body.non_relevant))
    )
    relevant = [marked[d] for d in body.relevant if d in marked]
    non_relevant = [marked[d] for d in body.non_relevant if d in marked]

    updated = rocchio_module.rocchio(
        previous,
        relevant,
        non_relevant,
        coefficients["alpha"],
        coefficients["beta"],
        coefficients["gamma"],
    )
    updated = rocchio_module.truncate(updated, settings.search.rocchio_max_terms)
    summary = rocchio_module.diff(previous, updated)

    page = await rocchio_module.rank_sparse_query(
        session, updated, SearchFilters(), body.limit, query_lemmas=parsed.lemmas
    )
    point = project(basis, column_of_term, updated)

    previous_ranks: dict[int, int] = {}
    if iterations:
        previous_ranks = {int(d): i + 1 for i, d in enumerate(iterations[-1].get("top", []))}

    lemmas = await _lemmas(session, sorted(set(updated) | set(previous)))
    titles = (
        {
            int(d): (str(t), str(u))
            for d, t, u in (
                await session.execute(
                    select(Document.id, Document.title, Document.url).where(
                        Document.id.in_([doc.document_id for doc in page.documents])
                    )
                )
            ).all()
        }
        if page.documents
        else {}
    )

    iteration_number = len(iterations) + 1
    entry: dict[str, Any] = {
        "iteration": iteration_number,
        "relevant": list(body.relevant),
        "non_relevant": list(body.non_relevant),
        "vector": {str(k): v for k, v in updated.items()},
        "projection": point,
        "top": [doc.document_id for doc in page.documents],
        "added_terms": [[lemmas.get(t, f"#{t}"), w] for t, w in summary.added],
        **coefficients,
    }
    # Reassigned, not appended in place: SQLAlchemy does not track JSONB mutation.
    feedback_session.iterations = [*iterations, entry]
    feedback_session.iteration_count = iteration_number
    feedback_session.alpha = coefficients["alpha"]
    feedback_session.beta = coefficients["beta"]
    feedback_session.gamma = coefficients["gamma"]
    await session.flush()

    log.info(
        "feedback_applied",
        session_id=feedback_session.id,
        iteration=iteration_number,
        relevant=len(relevant),
        non_relevant=len(non_relevant),
        terms=len(updated),
        added=len(summary.added),
    )

    return FeedbackOut(
        session_id=feedback_session.id,
        iteration=iteration_number,
        original_query=feedback_session.original_query,
        coefficients=coefficients,
        query_point=point,
        query_terms=_terms_out(updated, lemmas, previous, set(original)),
        added_terms=_terms_out(dict(summary.added), lemmas, None, set(original)),
        dropped_terms=[lemmas.get(t, f"#{t}") for t in summary.dropped],
        ranking=[
            RankingEntryOut(
                rank=rank,
                document_id=doc.document_id,
                title=titles.get(doc.document_id, ("(untitled)", ""))[0],
                url=titles.get(doc.document_id, ("", ""))[1],
                score=doc.score,
                matched_lemmas=doc.matched_lemmas,
                previous_rank=previous_ranks.get(doc.document_id),
            )
            for rank, doc in enumerate(page.documents, start=1)
        ],
        total_candidates=page.total_candidates,
        history=[_iteration_out(it) for it in feedback_session.iterations],
        index_version=index_version,
    )


@router.get("/feedback/{session_id}", response_model=list[IterationOut], summary="Replay a session")
async def feedback_history(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> list[IterationOut]:
    feedback_session = await session.get(FeedbackSession, session_id)
    if feedback_session is None:
        raise HTTPException(status_code=404, detail=f"feedback session {session_id} not found")
    return [_iteration_out(it) for it in feedback_session.iterations]


def _iteration_out(entry: dict[str, Any]) -> IterationOut:
    return IterationOut(
        iteration=int(entry.get("iteration", 0)),
        relevant=[int(x) for x in entry.get("relevant", [])],
        non_relevant=[int(x) for x in entry.get("non_relevant", [])],
        projection=[float(x) for x in entry.get("projection", [])],
        top=[int(x) for x in entry.get("top", [])],
        term_count=len(entry.get("vector", {})),
        alpha=float(entry.get("alpha", 0.0)),
        beta=float(entry.get("beta", 0.0)),
        gamma=float(entry.get("gamma", 0.0)),
    )
