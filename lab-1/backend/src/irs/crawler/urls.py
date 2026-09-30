"""URL normalisation and link extraction.

Canonicalisation matters more than it looks: the same page reached as
``http://Example.COM/a?b=1&utm_source=x#frag`` and ``https://example.com/a?b=1`` must be
recognised as one URL, or the crawler will fetch it repeatedly and the collection will
fill with duplicates that skew every inverse frequency.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

#: Query parameters that identify a campaign or session rather than content. Stripping
#: them collapses many URLs onto the page they actually address.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_source_platform",
        "gclid",
        "fbclid",
        "yclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "session",
        "sessionid",
        "sid",
        "phpsessid",
        "jsessionid",
        "_ga",
        "igshid",
        "spm",
    }
)

#: Extensions that are certainly not HTML. Checked before fetching, to avoid downloading
#: a large binary only to reject it on content type.
_NON_HTML_SUFFIXES = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".zip",
    ".gz",
    ".tar",
    ".rar",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".bmp",
    ".tiff",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".ogg",
    ".wav",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".rss",
    ".atom",
    ".exe",
    ".dmg",
    ".iso",
    ".apk",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)

_DEFAULT_PORTS = {"http": "80", "https": "443"}


def canonicalize(url: str) -> str | None:
    """Return a canonical form of ``url``, or ``None`` if it is not crawlable.

    Applies, in order: scheme/host lowercasing, default-port removal, fragment removal,
    tracking-parameter stripping, query-parameter sorting, and empty-path normalisation.
    Sorting the query is safe for retrieval purposes and collapses orderings of the same
    parameters onto one key.
    """
    if not url:
        return None

    url = url.strip()
    if not url or url.startswith(("mailto:", "javascript:", "tel:", "data:", "#")):
        return None

    try:
        parts = urlsplit(url)
    except ValueError:
        return None

    if parts.scheme not in ("http", "https"):
        return None
    if not parts.hostname:
        return None

    host = parts.hostname.lower()
    port = parts.port
    netloc = host
    if port and str(port) != _DEFAULT_PORTS.get(parts.scheme):
        netloc = f"{host}:{port}"

    path = parts.path or "/"
    # A trailing slash on a directory-like path is not meaningful; on a file-like path it
    # is left alone, since some servers distinguish them.
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))

    return urlunsplit((parts.scheme, netloc, path, query, ""))


def looks_like_html(url: str) -> bool:
    """Cheap pre-fetch filter on the URL's apparent type."""
    path = urlsplit(url).path.lower()
    return not path.endswith(_NON_HTML_SUFFIXES)


def registrable_host(url: str) -> str:
    """The host, without a leading ``www.``.

    Used for the same-domain restriction so that ``www.example.com`` and
    ``example.com`` are treated as one site, which they almost always are.
    """
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(left: str, right: str) -> bool:
    return registrable_host(left) == registrable_host(right)


def extract_links(html: str, base_url: str, limit: int = 500) -> list[str]:
    """Extract canonical, crawlable links from a page.

    Uses selectolax rather than a regular expression or a full DOM library: it is a
    C-backed HTML5 parser, so it handles real-world malformed markup at a fraction of the
    cost of lxml's tree building, and link extraction is on the hot path of every fetch.

    ``rel="nofollow"`` is honoured, and duplicates are collapsed while preserving
    document order so that a truncated list keeps the page's most prominent links.
    """
    try:
        tree = HTMLParser(html)
    except Exception:
        return []

    # A <base href> changes what relative links resolve against.
    base = base_url
    base_node = tree.css_first("base[href]")
    if base_node is not None:
        candidate = (base_node.attributes.get("href") or "").strip()
        if candidate:
            base = urljoin(base_url, candidate)

    seen: set[str] = set()
    links: list[str] = []

    for node in tree.css("a[href]"):
        if len(links) >= limit:
            break

        rel = (node.attributes.get("rel") or "").lower()
        if "nofollow" in rel:
            continue

        href = (node.attributes.get("href") or "").strip()
        if not href:
            continue

        try:
            absolute = urljoin(base, href)
        except ValueError:
            continue

        canonical = canonicalize(absolute)
        if canonical and canonical not in seen and looks_like_html(canonical):
            seen.add(canonical)
            links.append(canonical)

    return links
