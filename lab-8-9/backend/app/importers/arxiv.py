"""arXiv papers: metadata from the arXiv API, text from the LaTeXML HTML rendering.

arXiv serves most papers as structured HTML (arxiv.org/html/<id>, ar5iv for older
ones). Unlike a PDF it has real sections and paragraphs, and every formula carries its
LaTeX source in ``<math alttext>``, which the normalizer can verbalise. Only when no
HTML exists does the importer fall back to the PDF.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx
from selectolax.parser import HTMLParser, Node

from app.importers import pdf
from app.importers.structure import ImportedDocument, RawBlock, clean_text

log = logging.getLogger(__name__)

_ID = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*|^)(?P<id>\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)
HEADERS = {"User-Agent": "Lector/1.0 (voice reader for research papers; local use)"}
_SKIP = {"figure", "nav", "footer", "header", "script", "style"}
_SKIP_CLASSES = frozenset(
    {
        "ltx_bibliography",
        "ltx_note",
        "ltx_figure",
        "ltx_table",
        "ltx_tabular",
        "ltx_authors",
        "ltx_page_footer",
        "ltx_page_header",
        "ltx_dates",
        "ltx_toc",
        "ltx_listing",
        "ltx_algorithm",
        "ltx_float",
        "ltx_appendix",
    }
)


class ArxivError(Exception):
    pass


def parse_id(value: str) -> str | None:
    m = _ID.search(value.strip())
    return m.group("id") if m else None


def fetch_metadata(client: httpx.Client, arxiv_id: str) -> dict[str, object]:
    r = client.get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id})
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.text)
    entry = root.find("a:entry", ns)
    if entry is None or entry.find("a:title", ns) is None:
        raise ArxivError(f"arXiv has no paper {arxiv_id}")
    title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
    abstract = clean_text(entry.findtext("a:summary", default="", namespaces=ns))
    authors = [
        clean_text(a.findtext("a:name", default="", namespaces=ns))
        for a in entry.findall("a:author", ns)
    ]
    return {"title": title, "abstract": abstract, "authors": [a for a in authors if a]}


def _classes(node: Node) -> set[str]:
    return set((node.attributes.get("class") or "").split())


def _skipped(node: Node) -> bool:
    cur: Node | None = node
    while cur is not None:
        if cur.tag in _SKIP:
            return True
        if _classes(cur) & _SKIP_CLASSES:
            return True
        cur = cur.parent
    return False


def _inline_text(node: Node) -> str:
    """Text of a paragraph with formulas as \\( LaTeX \\) and footnotes removed."""
    parts: list[str] = []

    def walk(n: Node) -> None:
        for child in n.iter(include_text=True):
            if child.tag == "-text":
                parts.append(child.text(deep=False) or "")
                continue
            cls = _classes(child)
            if child.tag == "math":
                tex = (child.attributes.get("alttext") or child.text() or "").strip()
                display = child.attributes.get("display") == "block"
                if tex and not display:
                    parts.append(f" \\({tex}\\) ")
                continue
            if "ltx_note" in cls:
                continue
            if child.tag in {"script", "style", "button", "svg", "img"}:
                continue
            if "ltx_tag_note" in cls:
                continue
            walk(child)

    walk(node)
    # Formulas were padded with spaces; do not leave one before punctuation ("d_k , and").
    return re.sub(r"\s+([,.;:!?)\]])", r"\1", clean_text("".join(parts)))


def parse_html(html: str) -> ImportedDocument:
    tree = HTMLParser(html)
    root = tree.css_first("article") or tree.body
    if root is None:
        raise ArxivError("empty HTML")
    title_node = root.css_first("h1.ltx_title_document") or tree.css_first("title")
    title = _inline_text(title_node) if title_node else "Untitled paper"
    title = re.sub(r"\s*\\\((.*?)\\\)\s*", r" \1 ", title).strip()
    blocks: list[RawBlock] = []

    abstract = root.css_first("div.ltx_abstract")
    if abstract is not None:
        blocks.append(RawBlock("heading", "Abstract", 1))
        for p in abstract.css("p.ltx_p"):
            text = _inline_text(p)
            if text:
                blocks.append(RawBlock("paragraph", text))

    for node in _document_order(root):
        if _skipped(node) or (abstract is not None and _within(node, abstract)):
            continue
        if node.tag in {"h2", "h3", "h4"}:
            text = _inline_text(node)
            if text:
                level = {"h2": 1, "h3": 2, "h4": 3}[node.tag]
                blocks.append(
                    RawBlock("heading", re.sub(r"^(\d+(?:\.\d+)*)\s*", r"\1 ", text), level)
                )
        elif node.tag == "table":
            maths = [m.attributes.get("alttext") or "" for m in node.css("math")]
            tex = " ".join(t for t in maths if t).strip()
            if tex:
                blocks.append(RawBlock("equation", f"\\({tex}\\)"))
        else:
            text = _inline_text(node)
            if text and len(text) > 1:
                blocks.append(RawBlock("item" if _in_list_item(node) else "paragraph", text))
    return ImportedDocument(title=title, blocks=blocks)


def _document_order(root: Node) -> list[Node]:
    """Headings, paragraphs and display equations in reading order."""
    out: list[Node] = []
    for node in root.traverse(include_text=False):
        cls = _classes(node)
        if (
            (node.tag in {"h2", "h3", "h4"} and "ltx_title" in cls)
            or (node.tag == "p" and "ltx_p" in cls)
            or (node.tag == "table" and "ltx_equation" in cls)
        ):
            out.append(node)
    return out


def _in_list_item(node: Node) -> bool:
    cur = node.parent
    for _ in range(4):
        if cur is None:
            return False
        if cur.tag == "li":
            return True
        cur = cur.parent
    return False


def _within(node: Node, ancestor: Node) -> bool:
    cur = node.parent
    while cur is not None:
        if cur.mem_id == ancestor.mem_id:
            return True
        cur = cur.parent
    return False


def import_arxiv(value: str, client: httpx.Client | None = None) -> ImportedDocument:
    arxiv_id = parse_id(value)
    if not arxiv_id:
        raise ArxivError("That does not look like an arXiv ID or link.")
    own = client is None
    client = client or httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)
    try:
        meta = fetch_metadata(client, arxiv_id)
        doc: ImportedDocument | None = None
        for url in (
            f"https://arxiv.org/html/{arxiv_id}",
            f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
        ):
            try:
                r = client.get(url)
            except httpx.HTTPError:
                continue
            if r.status_code == 200 and "ltx_document" in r.text:
                doc = parse_html(r.text)
                if sum(1 for b in doc.blocks if b.kind == "paragraph") >= 3:
                    break
                doc = None
        if doc is None:
            r = client.get(f"https://arxiv.org/pdf/{arxiv_id}")
            r.raise_for_status()
            doc = pdf.parse(r.content)
        doc.title = str(meta["title"]) or doc.title
        doc.authors = list(meta["authors"])  # type: ignore[call-overload]
        doc.source = {"kind": "arxiv", "id": arxiv_id, "url": f"https://arxiv.org/abs/{arxiv_id}"}
        if (
            not any(b.kind == "heading" and b.text.lower() == "abstract" for b in doc.blocks)
            and meta["abstract"]
        ):
            doc.blocks[:0] = [
                RawBlock("heading", "Abstract", 1),
                RawBlock("paragraph", str(meta["abstract"])),
            ]
        return doc
    finally:
        if own:
            client.close()
