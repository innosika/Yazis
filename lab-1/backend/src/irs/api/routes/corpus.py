"""Collection browsing: documents, their automatically extracted keywords, statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from irs.api.schemas import (
    CollectionStatsOut,
    DocumentDetailOut,
    DocumentSummaryOut,
    KeywordOut,
)
from irs.config import settings
from irs.db.models import Document, Posting, Term
from irs.db.session import get_session
from irs.index.builder import IndexBuilder, get_collection_stat
from irs.index.weights import inverse_frequency, raw_weight
from irs.logging import get_logger

log = get_logger("irs.api.corpus")
router = APIRouter(prefix="/corpus", tags=["corpus"])


@router.get("/stats", response_model=CollectionStatsOut, summary="Collection statistics")
async def stats(session: AsyncSession = Depends(get_session)) -> CollectionStatsOut:
    """`N`, `D` and the index's provenance.

    Reports whether the index is stale by comparing the live document and term counts
    against the values recorded at the last build — because every weight in the
    collection depends on `N`, a stale index silently returns wrong scores, and that is
    worth surfacing rather than hiding.
    """
    stat = await get_collection_stat(session)
    live_documents = int(
        (await session.execute(select(func.count()).select_from(Document))).scalar_one()
    )
    live_terms = int((await session.execute(select(func.count()).select_from(Term))).scalar_one())

    return CollectionStatsOut(
        document_count=stat.document_count,
        term_count=stat.term_count,
        posting_count=stat.posting_count,
        average_document_length=stat.average_document_length,
        index_version=stat.index_version,
        log_base=stat.log_base,
        built_at=stat.built_at,
        build_duration_ms=stat.build_duration_ms,
        embedded_document_count=stat.embedded_document_count,
        is_stale=(live_documents != stat.document_count or live_terms != stat.term_count),
    )


@router.get("/documents", response_model=list[DocumentSummaryOut], summary="List documents")
async def list_documents(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    domain: str | None = Query(default=None, max_length=255),
    search: str | None = Query(default=None, max_length=200, description="Title/URL substring"),
) -> list[DocumentSummaryOut]:
    statement = select(Document).order_by(Document.id).offset(offset).limit(limit)
    if domain:
        statement = statement.where(Document.source_domain == domain)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(Document.title.ilike(pattern) | Document.url.ilike(pattern))

    documents = (await session.execute(statement)).scalars().all()
    return [
        DocumentSummaryOut(
            id=document.id,
            url=document.url,
            title=document.title,
            source_domain=document.source_domain,
            published_at=document.published_at,
            fetched_at=document.fetched_at,
            language=document.language,
            token_count=document.token_count,
            distinct_term_count=document.distinct_term_count,
            vector_norm=document.vector_norm,
            has_embedding=document.embedding is not None,
        )
        for document in documents
    ]


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailOut,
    summary="One document with its extracted keywords",
)
async def get_document(
    document_id: int, session: AsyncSession = Depends(get_session)
) -> DocumentDetailOut:
    """Fetch a document together with the keywords the system extracted for it.

    Keywords are ranked by `A_i^j = Q_i^j · B_i` — formula 1.6, which the assignment
    specifies for automatic keyword extraction. The normalized ranking weight `w_dk` is
    returned alongside so the two can be compared: they order terms differently, and
    seeing that is the clearest way to understand why the assignment specifies each one
    for a different purpose.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"document {document_id} not found"
        )

    stat = await get_collection_stat(session)
    rows = (
        await session.execute(
            select(
                Term.lemma,
                Term.document_frequency,
                Posting.term_frequency,
                Posting.weight_raw,
                Posting.weight_norm,
            )
            .join(Posting, Posting.term_id == Term.id)
            .where(Posting.document_id == document_id)
            .order_by(Posting.weight_raw.desc(), Term.lemma)
            .limit(settings.index.keywords_per_document)
        )
    ).all()

    keywords = [
        KeywordOut(
            lemma=row.lemma,
            term_frequency=row.term_frequency,
            document_frequency=row.document_frequency,
            inverse_frequency=inverse_frequency(stat.document_count, row.document_frequency),
            weight_raw=row.weight_raw
            or raw_weight(
                row.term_frequency,
                inverse_frequency(stat.document_count, row.document_frequency),
            ),
            weight_norm=row.weight_norm,
        )
        for row in rows
    ]

    return DocumentDetailOut(
        id=document.id,
        url=document.url,
        title=document.title,
        source_domain=document.source_domain,
        published_at=document.published_at,
        fetched_at=document.fetched_at,
        language=document.language,
        token_count=document.token_count,
        distinct_term_count=document.distinct_term_count,
        vector_norm=document.vector_norm,
        has_embedding=document.embedding is not None,
        text=document.text,
        description=document.description,
        author=document.author,
        http_status=document.http_status,
        byte_size=document.byte_size,
        keywords=keywords,
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a document from the collection",
)
async def delete_document(
    document_id: int,
    reindex: bool = Query(
        default=True,
        description=(
            "Recompute every term weight afterwards. Deleting a document changes N, "
            "which changes every inverse frequency in the collection."
        ),
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Back the assignment's ``Document.DeleteDocumentFromBase``.

    Reweighting defaults to on because `B_i = log(N / P_i)` depends on the collection
    size: after a deletion every stored weight is stale, so leaving the index untouched
    would return subtly wrong scores rather than obviously broken ones.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"document {document_id} not found"
        )

    url = document.url
    await session.execute(delete(Document).where(Document.id == document_id))
    log.info("document_deleted", document_id=document_id, url=url)

    stats = None
    if reindex:
        # `reanalyze=False`: the remaining documents' term counts are unchanged, only the
        # weights that depend on N need recomputing. That is a handful of SQL statements
        # rather than a full re-analysis of the collection.
        stats = await IndexBuilder(session).rebuild(reanalyze=False)

    return {
        "deleted": document_id,
        "url": url,
        "reindexed": reindex,
        "stats": stats.as_dict() if stats else None,
    }


@router.post("/index", summary="Rebuild the index")
async def rebuild_index(
    weights_only: bool = Query(
        default=False,
        description="Keep existing term counts and recompute only the weights.",
    ),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Rebuild the inverted index and every term weight."""
    stats = await IndexBuilder(session).rebuild(reanalyze=not weights_only)
    return {"status": "ok", "stats": stats.as_dict()}


class AddDocumentIn(BaseModel):
    """The assignment's ``Document.AddDocumentToBase``: one page by URL."""

    url: str = Field(min_length=8, max_length=2_048)


class AddDocumentOut(BaseModel):
    crawl_job_id: int
    url: str
    status: str
    message: str


@router.post(
    "/documents",
    response_model=AddDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Add one document by URL",
)
async def add_document(
    body: AddDocumentIn, session: AsyncSession = Depends(get_session)
) -> AddDocumentOut:
    """Fetch, extract, de-duplicate and index a single page.

    Implemented as a one-page crawl job so the page goes through exactly the same
    pipeline as the rest of the corpus — robots.txt, boilerplate removal, SimHash
    near-duplicate rejection, indexing — and its progress is visible on the Crawl screen.
    """
    from irs.crawler.service import create_job
    from irs.crawler.tasks import run_crawl_job

    try:
        job = await create_job(
            session, seed_urls=[body.url], max_pages=1, max_depth=0, same_domain_only=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()

    try:
        handle = await run_crawl_job.kiq(job.id)
        job.task_id = handle.task_id
        await session.commit()
    except Exception as exc:
        log.error("add_document_enqueue_failed", job_id=job.id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"the page was queued as crawl job {job.id} but the worker is unreachable: {exc}"
            ),
        ) from exc

    return AddDocumentOut(
        crawl_job_id=job.id,
        url=body.url,
        status=str(job.status),
        message="queued as a one-page crawl; follow it on the Crawl screen",
    )
