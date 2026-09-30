from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import models
from app.db.base import session
from app.importers import arxiv, pdf, serialize, web
from app.importers import text as text_importer
from app.importers.structure import ImportedDocument, build

router = APIRouter(prefix="/documents", tags=["documents"])

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_article.md"
WORDS_PER_MINUTE = 155  # measured Kokoro pace at speed 1.0
MAX_UPLOAD = 40 * 1024 * 1024


class DocumentSummary(BaseModel):
    id: str
    title: str
    authors: list[str]
    source: dict[str, Any]
    word_count: int
    minutes: float
    progress: float
    sections: int
    created_at: datetime
    opened_at: datetime


class DocumentOut(DocumentSummary):
    structure: dict[str, Any]
    position: dict[str, Any]


class TextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=500_000)
    title: str | None = Field(None, max_length=300)


class ImportIn(BaseModel):
    source: str = Field(..., min_length=3, max_length=2000, description="arXiv ID/link or any URL")


class DocumentSource(BaseModel):
    title: str
    authors: list[str]
    text: str


class DocumentPatch(BaseModel):
    """Any subset: rename, change the authors, or replace the whole text."""

    title: str | None = Field(None, max_length=500)
    authors: list[str] | None = Field(None, max_length=100)
    text: str | None = Field(None, max_length=500_000)


class PositionIn(BaseModel):
    block: int = Field(..., ge=0)
    sentence: int = Field(0, ge=0)
    progress: float = Field(0.0, ge=0.0, le=1.0)


def _summary(d: models.Document) -> DocumentSummary:
    return DocumentSummary(
        id=d.id,
        title=d.title,
        authors=d.authors or [],
        source=d.source or {},
        word_count=d.word_count,
        minutes=round(d.word_count / WORDS_PER_MINUTE, 1),
        progress=d.progress,
        sections=len((d.structure or {}).get("sections", [])),
        created_at=d.created_at,
        opened_at=d.opened_at,
    )


def _full(d: models.Document) -> DocumentOut:
    return DocumentOut(**_summary(d).model_dump(), structure=d.structure, position=d.position or {})


def _store(doc: ImportedDocument) -> DocumentOut:
    structure = build(doc)
    if not structure["blocks"]:
        raise HTTPException(422, "No readable text found.")
    with session() as s:
        row = models.Document(
            id=uuid.uuid4().hex[:16],
            title=doc.title[:500] or "Untitled",
            authors=doc.authors,
            source=doc.source,
            structure=structure,
            word_count=structure["word_count"],
            position={},
            progress=0.0,
        )
        s.add(row)
        s.flush()
        return _full(row)


def seed_sample() -> None:
    """Put the built-in article in an empty library so the first run has something to read."""
    with session() as s:
        if s.scalar(select(models.Document.id).limit(1)) is not None:
            return
    doc = text_importer.parse(SAMPLE_FILE.read_text(encoding="utf-8"))
    doc.authors = ["Lector"]
    doc.source = {"kind": "sample"}
    _store(doc)


@router.get("", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    with session() as s:
        rows = s.scalars(select(models.Document).order_by(models.Document.opened_at.desc())).all()
        return [_summary(r) for r in rows]


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str) -> DocumentOut:
    with session() as s:
        row = s.get(models.Document, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        row.opened_at = datetime.now(UTC)
        return _full(row)


@router.post("/text", response_model=DocumentOut, status_code=201)
def create_from_text(body: TextIn) -> DocumentOut:
    doc = text_importer.parse(body.text, title=body.title or None)
    doc.source = {"kind": "text"}
    return _store(doc)


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload(file: UploadFile = File(...)) -> DocumentOut:
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "The file is larger than 40 MB.")
    name = file.filename or "document"
    lower = name.lower()
    try:
        if lower.endswith(".pdf") or data[:5] == b"%PDF-":
            doc = await asyncio.to_thread(pdf.parse, data, name)
        elif lower.endswith((".txt", ".md", ".markdown", ".text")):
            text = data.decode("utf-8", errors="replace")
            doc = text_importer.parse(text)
            doc.source = {"kind": "file", "filename": name}
        else:
            raise HTTPException(415, "Upload a PDF, a .txt or a .md file.")
    except pdf.PdfError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _store(doc)


@router.post("/import", response_model=DocumentOut, status_code=201)
async def import_source(body: ImportIn) -> DocumentOut:
    src = body.source.strip()
    try:
        if arxiv.parse_id(src) and ("arxiv" in src.lower() or "/" not in src):
            doc = await asyncio.to_thread(arxiv.import_arxiv, src)
        else:
            doc = await asyncio.to_thread(web.import_url, src)
    except (arxiv.ArxivError, web.WebError, pdf.PdfError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Import failed: {exc}") from exc
    return _store(doc)


@router.get("/{doc_id}/source", response_model=DocumentSource)
def document_source(doc_id: str) -> DocumentSource:
    """The document as editable text (see app.importers.serialize for the format)."""
    with session() as s:
        row = s.get(models.Document, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        text = serialize.to_text((row.structure or {}).get("blocks", []))
        return DocumentSource(title=row.title, authors=row.authors or [], text=text)


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: str, body: DocumentPatch) -> DocumentOut:
    with session() as s:
        row = s.get(models.Document, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        if body.title is not None:
            title = " ".join(body.title.split())
            if not title:
                raise HTTPException(422, "The title cannot be empty.")
            row.title = title
        if body.authors is not None:
            row.authors = [a.strip() for a in body.authors if a.strip()][:100]
        if body.text is not None:
            parsed = text_importer.parse(body.text, title=row.title, strict=True)
            # What the user wrote is kept in full, a "References" heading included.
            structure = build(parsed, drop_after_references=False)
            if not structure["blocks"]:
                raise HTTPException(
                    422, "The text is empty. Write something to read, or delete the document."
                )
            row.structure = structure
            row.word_count = structure["word_count"]
            row.position = _clamp_position(row.position or {}, structure)
            if not row.position:
                row.progress = 0.0
        return _full(row)


def _clamp_position(position: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    """Keep the reading position when the edited text still has that sentence."""
    blocks = structure["blocks"]
    block = int(position.get("block", 0))
    if not position or block >= len(blocks):
        return {}
    sentences = blocks[block]["sentences"]
    sentence = min(int(position.get("sentence", 0)), max(0, len(sentences) - 1))
    return {"block": block, "sentence": sentence}


@router.patch("/{doc_id}/position", response_model=DocumentSummary)
def save_position(doc_id: str, body: PositionIn) -> DocumentSummary:
    with session() as s:
        row = s.get(models.Document, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        row.position = {"block": body.block, "sentence": body.sentence}
        row.progress = body.progress
        return _summary(row)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str) -> None:
    with session() as s:
        row = s.get(models.Document, doc_id)
        if row is None:
            raise HTTPException(404, "Document not found")
        s.delete(row)
