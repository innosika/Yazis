"""Main-content extraction: HTML → title, text, date, language.

Boilerplate removal is what makes a crawled collection usable. A raw HTML page is mostly
navigation, footers, cookie notices and advertising; indexing that vocabulary would give
site chrome the same standing as a document's actual subject, and since the chrome
repeats across every page of a site it would dominate the term statistics.

trafilatura is used rather than a hand-written heuristic. It is the strongest open
boilerplate remover on published benchmarks, and it also recovers the metadata the
assignment's ``Document`` class needs — title and date — in the same pass.
"""

from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from datetime import date, datetime

import trafilatura
from trafilatura.settings import use_config

from irs.config import settings
from irs.logging import get_logger

log = get_logger("irs.crawler.extract")


def _build_config() -> ConfigParser:
    """trafilatura configuration.

    Its default is to sample the network for metadata resolution; that is disabled so
    extraction stays a pure function of the HTML we already fetched, which keeps the
    crawl's request count equal to its page count.
    """
    config = use_config()
    config.set("DEFAULT", "EXTRACTION_TIMEOUT", "20")
    config.set("DEFAULT", "MIN_EXTRACTED_SIZE", str(settings.crawler.min_extracted_chars))
    config.set("DEFAULT", "MIN_OUTPUT_SIZE", str(settings.crawler.min_extracted_chars))
    return config


_CONFIG = _build_config()


@dataclass(slots=True)
class Extracted:
    """The usable content of one page."""

    title: str
    text: str
    published_at: date | None = None
    language: str | None = None
    author: str | None = None
    description: str | None = None
    #: trafilatura's own content fingerprint, kept for cross-checking our deduplication.
    fingerprint: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)


def extract(html: str, url: str) -> Extracted | None:
    """Extract the main content of a page.

    Returns ``None`` when nothing usable was found — a navigation-only page, a redirect
    stub, or markup trafilatura cannot make sense of. That is a normal outcome on a real
    crawl, not an error, and the caller records it as a skip with a reason.

    ``favor_precision`` is set because a collection of clean short documents produces
    better term statistics than one where every document trails a footer; recall of body
    text matters less here than not polluting the dictionary.
    """
    if not html:
        return None

    try:
        document = trafilatura.bare_extraction(
            html,
            url=url,
            with_metadata=True,
            favor_precision=True,
            include_comments=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            deduplicate=True,
            config=_CONFIG,
        )
    except Exception as exc:
        log.debug("extraction_error", url=url[:200], error=str(exc))
        return None

    if document is None:
        return None

    text = _clean(_attr(document, "text") or "")
    if len(text) < settings.crawler.min_extracted_chars:
        return None

    return Extracted(
        title=_clean(_attr(document, "title") or "")[:1_000],
        text=text,
        published_at=_parse_date(_attr(document, "date")),
        language=(_attr(document, "language") or None),
        author=(_clean(_attr(document, "author") or "") or None),
        description=(_clean(_attr(document, "description") or "") or None),
        fingerprint=_attr(document, "fingerprint"),
    )


def _attr(document: object, name: str) -> str | None:
    """Read a field from trafilatura's result.

    It returns a ``Document`` object in current versions and a plain dict in older ones;
    supporting both keeps a minor upgrade from breaking extraction.
    """
    value = document.get(name) if isinstance(document, dict) else getattr(document, name, None)
    return value if isinstance(value, str) else None


def _clean(text: str) -> str:
    """Normalise whitespace while preserving paragraph breaks.

    Paragraph structure is kept because the snippet builder positions its window by
    character offset, and collapsing everything to one line would make snippets
    read as run-on text.
    """
    lines = [line.strip() for line in (text or "").splitlines()]
    kept: list[str] = []
    for line in lines:
        if line:
            kept.append(" ".join(line.split()))
        elif kept and kept[-1] != "":
            kept.append("")
    return "\n".join(kept).strip()


def _parse_date(value: str | None) -> date | None:
    """Parse trafilatura's date, which is normally ISO but not guaranteed to be."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip()[: len(fmt.replace("%Y", "0000"))], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.strip()[:10]).date()
    except ValueError:
        return None
