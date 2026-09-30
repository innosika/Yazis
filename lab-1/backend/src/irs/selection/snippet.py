"""Snippet construction and query-term highlighting.

The assignment requires each result to expose a ``snippet`` (the first ~300 characters)
and the list of query words present in the document. Two things are produced here:

* a **query-biased** snippet — a window of the text centred on where the query terms
  actually occur, rather than the document's opening sentence, because the opening
  sentence usually says nothing about the query;
* the character ranges to highlight, computed on the server so that the client never has
  to re-tokenise the text and cannot disagree with the index about what matched.

The assignment's literal "first 300 characters" is kept available as a fallback for
documents where no query term is located in the extracted text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from irs.config import settings
from irs.nlp.pipeline import analyzer

#: Word-ish runs, used to align lemmas back onto their surface forms in the raw text.
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*|\d+")

#: How far into a document to look for query-term occurrences. Bounds the linguistic
#: pass; a match beyond this point would not make a better snippet than one before it.
HORIZON_CHARS = 6_000

#: Process-wide surface-form → lemma cache.
#:
#: Highlighting needs the lemma of every word in the candidate region, and running the
#: tagger over that region was the dominant cost of a search. English text reuses its
#: vocabulary heavily, both within a document and across a collection, so after a few
#: searches almost every word is already known and the linguistic pass can be skipped
#: outright. Bounded so a large crawl cannot grow it without limit.
#:
#: The cache is keyed on the surface form alone, so it loses in-context disambiguation
#: (the "saw" noun/verb case). That is acceptable *here* and only here: this cache
#: decides whether to mark a word in a snippet, never what gets indexed or scored. The
#: index itself is always built with full context.
_LEMMA_CACHE: dict[str, str] = {}
_LEMMA_CACHE_MAX = 200_000


@dataclass(slots=True)
class Highlight:
    """A character range in the snippet to mark, and the lemma that caused it."""

    start: int
    end: int
    lemma: str


@dataclass(slots=True)
class Snippet:
    """A presentable fragment of a document."""

    text: str
    highlights: list[Highlight] = field(default_factory=list)
    #: True when the window was positioned on query matches rather than the text start.
    query_biased: bool = False
    #: Distinct query lemmas located inside the snippet.
    matched_lemmas: list[str] = field(default_factory=list)


def _locate_matches_batch(texts: list[str], wanted: set[str]) -> list[list[tuple[int, int, str]]]:
    """Locate the wanted lemmas in several texts using a single spaCy pass.

    The document's stored text is raw prose while the index holds lemmas, so surface
    forms must be mapped back. Lemmatising through the *same* pipeline used for indexing
    means "retrieving" in the text correctly matches the indexed lemma "retrieve", where
    a substring or prefix match would both miss real matches and invent false ones.

    Batched with ``nlp.pipe`` because doing this per document made snippet construction
    the dominant cost of a search — several hundred milliseconds for a page of ten
    results, against single-digit milliseconds for the ranking itself. The tagger and
    lemmatiser are the only components needed, so everything else is disabled.
    """
    if not wanted or not texts:
        return [[] for _ in texts]

    spans_per_text = [
        [(m.start(), m.end(), m.group(0)) for m in _WORD.finditer(text)] for text in texts
    ]

    # Only words the cache has never seen need the tagger.
    unknown = {
        span[2].lower()
        for spans in spans_per_text
        for span in spans
        if span[2].lower() not in _LEMMA_CACHE
    }
    if unknown:
        _learn_lemmas(unknown)

    located: list[list[tuple[int, int, str]]] = []
    for spans in spans_per_text:
        matches: list[tuple[int, int, str]] = []
        for start, end, word in spans:
            lowered = word.lower()
            lemma = _LEMMA_CACHE.get(lowered, lowered)
            if lemma in wanted:
                matches.append((start, end, lemma))
            elif lowered in wanted:
                # The surface form is itself an index term (common for plain nouns).
                matches.append((start, end, lowered))
        located.append(matches)

    return located


def _learn_lemmas(words: set[str]) -> None:
    """Lemmatise unseen surface forms and add them to the cache.

    Words are batched into a few long pseudo-sentences rather than tagged one at a time,
    because spaCy's per-call overhead dominates for single tokens.
    """
    if len(_LEMMA_CACHE) > _LEMMA_CACHE_MAX:
        _LEMMA_CACHE.clear()

    ordered = sorted(words)
    chunks = [" ".join(ordered[i : i + 400]) for i in range(0, len(ordered), 400)]

    for doc in analyzer.nlp.pipe(chunks, batch_size=8, disable=["ner"]):
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            _LEMMA_CACHE.setdefault(token.text.lower(), token.lemma_.lower())

    # Anything the tagger dropped maps to itself, so it is not looked up again.
    for word in ordered:
        _LEMMA_CACHE.setdefault(word, word)


def build_snippets(
    documents: list[tuple[str, str]],
    query_lemmas: list[str],
    max_chars: int | None = None,
) -> list[Snippet]:
    """Build query-biased snippets for a whole result page in one pass.

    Args:
        documents: ``(text, title)`` per result, in result order.
        query_lemmas: the query's search image.
        max_chars: snippet length; defaults to the configured 300 characters.
    """
    max_chars = settings.search.snippet_chars if max_chars is None else max_chars
    wanted = set(query_lemmas)

    bodies = [(text or "").strip() for text, _ in documents]
    # Searching a whole page is wasteful — the match is in the opening few thousand
    # characters in nearly every case, and this bounds the linguistic pass.
    horizons = [body[:HORIZON_CHARS] for body in bodies]
    matches_per_document = _locate_matches_batch(horizons, wanted)

    return [
        _assemble(body, matches, query_lemmas, max_chars)
        for body, matches in zip(bodies, matches_per_document, strict=True)
    ]


def build_snippet(
    text: str,
    title: str,
    query_lemmas: list[str],
    max_chars: int | None = None,
) -> Snippet:
    """Single-document convenience wrapper over :func:`build_snippets`."""
    return build_snippets([(text, title)], query_lemmas, max_chars)[0]


def _assemble(
    text: str,
    occurrences: list[tuple[int, int, str]],
    query_lemmas: list[str],
    max_chars: int,
) -> Snippet:
    """Choose the window, snap it to word boundaries and compute highlight ranges."""
    if not text:
        return Snippet(text="", query_biased=False)

    if not occurrences:
        # Fall back to the assignment's literal definition: the opening characters.
        start, end = _snap_to_words(text, 0, max_chars)
        return Snippet(
            text=_ellipsise(text, start, end),
            highlights=[],
            query_biased=False,
            matched_lemmas=[],
        )

    start, end = _densest_window(occurrences, len(text), max_chars)
    start, end = _snap_to_words(text, start, end - start)

    fragment = _ellipsise(text, start, end)
    # A leading ellipsis shifts every offset within the fragment by one character.
    prefix = 1 if start > 0 else 0

    highlights: list[Highlight] = []
    seen: set[str] = set()
    for occurrence_start, occurrence_end, lemma in occurrences:
        if start <= occurrence_start and occurrence_end <= end:
            highlights.append(
                Highlight(
                    start=occurrence_start - start + prefix,
                    end=occurrence_end - start + prefix,
                    lemma=lemma,
                )
            )
            seen.add(lemma)

    return Snippet(
        text=fragment,
        highlights=highlights,
        query_biased=True,
        matched_lemmas=[lemma for lemma in query_lemmas if lemma in seen],
    )


def _densest_window(
    occurrences: list[tuple[int, int, str]], text_length: int, width: int
) -> tuple[int, int]:
    """Find the window of ``width`` characters covering the most *distinct* query terms.

    Distinct rather than total occurrences: a passage mentioning three different query
    words is a better summary than one repeating a single word five times, and the latter
    is what a naive count would choose.
    """
    best_start = max(0, occurrences[0][0] - width // 3)
    best_distinct = -1
    best_total = -1

    for anchor_start, _, _ in occurrences:
        window_start = max(0, anchor_start - width // 3)
        window_end = window_start + width
        inside = [o for o in occurrences if window_start <= o[0] and o[1] <= window_end]
        distinct = len({o[2] for o in inside})
        total = len(inside)
        if (distinct, total) > (best_distinct, best_total):
            best_distinct, best_total = distinct, total
            best_start = window_start

    return best_start, min(text_length, best_start + width)


def _snap_to_words(text: str, start: int, width: int) -> tuple[int, int]:
    """Expand the window outward to the nearest word boundaries."""
    end = min(len(text), start + width)

    if start > 0:
        space = text.rfind(" ", max(0, start - 40), start + 1)
        start = space + 1 if space != -1 else start
    if end < len(text):
        space = text.find(" ", end)
        end = space if space != -1 and space - end < 40 else end

    return start, end


def _ellipsise(text: str, start: int, end: int) -> str:
    fragment = text[start:end].strip()
    if start > 0:
        fragment = f"…{fragment}"
    if end < len(text):
        fragment = f"{fragment}…"
    return fragment
