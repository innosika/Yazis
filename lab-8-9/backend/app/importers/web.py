"""Any other web page: main article text via trafilatura. arXiv links and PDFs are
routed to their own importers."""

from __future__ import annotations

import httpx
import trafilatura

from app.importers import arxiv, pdf
from app.importers import text as text_importer
from app.importers.structure import ImportedDocument


class WebError(Exception):
    pass


def import_url(url: str) -> ImportedDocument:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if "arxiv.org" in url and arxiv.parse_id(url):
        return arxiv.import_arxiv(url)
    try:
        with httpx.Client(headers=arxiv.HEADERS, timeout=30, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
    except httpx.HTTPError as exc:
        raise WebError(f"Could not download the page: {exc}") from exc
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        doc = pdf.parse(r.content, filename=url.rsplit("/", 1)[-1])
        doc.source = {**doc.source, "kind": "pdf", "url": url}
        return doc
    html = r.text
    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_images=False,
        include_tables=False,
        include_comments=False,
    )
    if not md or len(md) < 80:
        raise WebError("No readable article text on that page.")
    meta = trafilatura.extract_metadata(html)
    title = meta.title if meta and meta.title else None
    doc = text_importer.parse(md, title=title)
    if meta and meta.author:
        doc.authors = [a.strip() for a in meta.author.split(";") if a.strip()]
    doc.source = {"kind": "web", "url": url}
    return doc
