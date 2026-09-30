"""PDF papers via PyMuPDF4LLM: layout-aware reading order (two columns, headers and
footers removed), converted to Markdown and then parsed like any Markdown text."""

from __future__ import annotations

import re

import pymupdf
import pymupdf4llm

from app.importers import text as text_importer
from app.importers.structure import ImportedDocument


class PdfError(Exception):
    pass


def parse(data: bytes, filename: str = "document.pdf") -> ImportedDocument:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise PdfError("This file is not a readable PDF.") from exc
    if doc.page_count == 0:
        raise PdfError("The PDF has no pages.")
    try:
        md = pymupdf4llm.to_markdown(
            doc, header=False, footer=False, ignore_images=True, use_ocr=False, show_progress=False
        )
    except TypeError:
        md = pymupdf4llm.to_markdown(doc, ignore_images=True, show_progress=False)
    if not isinstance(md, str):
        md = "\n\n".join(chunk.get("text", "") for chunk in md)
    if len(md.strip()) < 50:
        raise PdfError("No text found in the PDF (is it a scan?).")
    meta_title = (doc.metadata or {}).get("title") or None
    md = _tidy(md)
    parsed = text_importer.parse(md, title=None, dehyphenate=True)
    if meta_title and len(meta_title) > 8 and not meta_title.lower().endswith((".pdf", ".dvi")):
        parsed.title = meta_title.strip()
    parsed.source = {"kind": "pdf", "filename": filename, "pages": doc.page_count}
    return parsed


def _tidy(md: str) -> str:
    md = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", md)  # bare page numbers
    md = re.sub(r"(?m)^\s*arXiv:\S+.*$", "", md)  # the arXiv side stamp
    md = re.sub(r"(?m)^#+\s*$", "", md)
    # PyMuPDF4LLM marks bold/italic spans; headings come as #/##, keep those.
    md = re.sub(r"(?<!\w)\*\*(.+?)\*\*(?!\w)", r"\1", md)
    return md
