"""Export endpoints: the Unicode `.txt` file required by R9."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import Document
from app.schemas.translate import TranslateRequest
from app.services import export
from app.services import translate as translate_service

router = APIRouter(prefix="/export", tags=["export"])


@router.post(
    "/txt",
    response_class=PlainTextResponse,
    summary="Translation and frequency list as a Unicode .txt file",
)
async def export_txt(
    request: TranslateRequest, session: AsyncSession = Depends(get_session)
) -> PlainTextResponse:
    """Re-run the translation and serialise it.

    Re-running rather than caching the last result keeps the export honest: the file always
    reflects the dictionary and the locked senses as they are now, not as they were when the
    browser last rendered a translation.
    """
    result, _ = await translate_service.translate(
        session,
        text=request.text,
        domain=request.domain,
        mode=request.mode,
        include_direct=request.include_direct,
        use_memory=request.use_memory,
        save=False,
        title=request.title,
    )
    title = request.title or "translation"
    content = export.build_txt(result, title=title)
    filename = export.safe_filename(title)
    export.save_txt(content, filename)
    return PlainTextResponse(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/documents", summary="Previous translation runs")
async def documents(limit: int = 20, session: AsyncSession = Depends(get_session)) -> list[dict]:
    from sqlalchemy import select

    rows = (
        await session.scalars(
            select(Document).order_by(Document.created_at.desc()).limit(min(limit, 100))
        )
    ).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "domain_code": row.domain_code,
            "mode": row.mode,
            "stats": row.stats,
            "duration_ms": row.duration_ms,
            "characters": len(row.source_text),
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in rows
    ]


@router.get("/documents/{document_id}", summary="Reopen a previous run's input")
async def document(document_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(Document, document_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return {
        "id": row.id,
        "title": row.title,
        "source_text": row.source_text,
        "domain_code": row.domain_code,
        "mode": row.mode,
        "stats": row.stats,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
