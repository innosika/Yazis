"""English linguistic pipeline: text → index terms.

Produces the *search image* (поисковый образ) of a text: the multiset of lemmas that
becomes a document's or a query's vector components.

The assignment states a constraint that shapes this module's interface: «поисковый образ
запроса и поисковый образ документа должны иметь одинаковую структуру в пределах одной
поисковой системы» — a query's search image and a document's must have the same
structure within one system. So documents and queries are analysed by the *same*
function, not by two similar ones that could drift apart. Any change to tokenisation,
lemmatisation or stop-word handling therefore applies to both sides automatically, which
is the only way `w_dk` and `w_qj` can be guaranteed to index the same dictionary.

spaCy's `en_core_web_sm` is used for lemmatisation because English lemmatisation is
POS-dependent — "saw" lemmatises to *see* or *saw* depending on whether it is a verb or
a noun, and a stemmer cannot make that distinction. The report's third-party components
section documents this choice.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from irs.config import settings
from irs.logging import get_logger

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc

log = get_logger("irs.nlp")

MODEL_NAME = "en_core_web_sm"

#: Components we never need. The dependency parser is the most expensive part of the
#: pipeline and contributes nothing to a bag-of-words index.
_EXCLUDED_COMPONENTS = ["parser", "senter"]

#: A token must contain at least one letter to be an index term. This rejects pure
#: punctuation, bare numbers and separator runs while keeping alphanumerics like "covid19".
_HAS_LETTER = re.compile(r"[a-zA-Z]")

#: Collapse runs of whitespace so that stored text and character offsets are stable.
_WHITESPACE = re.compile(r"\s+")

#: Domain-agnostic additions to spaCy's stop list: web boilerplate that survives
#: extraction often enough to pollute the dictionary.
_EXTRA_STOPWORDS: frozenset[str] = frozenset(
    {
        "cookie",
        "cookies",
        "javascript",
        "browser",
        "login",
        "signin",
        "signup",
        "subscribe",
        "newsletter",
        "advertisement",
        "privacy",
        "copyright",
        "reserved",
        "email",
        "click",
        "href",
        "http",
        "https",
        "www",
    }
)


@dataclass(slots=True)
class TermOccurrence:
    """One index term and where it occurs.

    Positions are token indices, not character offsets, because they are used for
    proximity scoring and snippet selection over the token stream.
    """

    lemma: str
    pos: str
    frequency: int
    positions: list[int] = field(default_factory=list)


@dataclass(slots=True)
class Entity:
    """A named entity, used only for the corpus browser's facets."""

    text: str
    label: str


@dataclass(slots=True)
class SearchImage:
    """The analysed form of a text — a document's ПОД or a query's ПОЗ."""

    #: Lemma → occurrence record. This *is* the sparse vector's index.
    terms: dict[str, TermOccurrence]
    #: Total tokens retained as index terms. BM25's `|d|`.
    token_count: int
    #: Tokens seen before filtering, for the report's filtering-yield figure.
    raw_token_count: int
    entities: list[Entity] = field(default_factory=list)
    #: Lemmas in first-appearance order. Query term highlighting and the "words of your
    #: query present in this document" list read this, so the order the user sees
    #: matches the order they typed.
    ordered_lemmas: list[str] = field(default_factory=list)

    @property
    def distinct_term_count(self) -> int:
        return len(self.terms)

    def frequencies(self) -> dict[str, int]:
        """``lemma → N_dk``, the raw counts the weighting formulas consume."""
        return {lemma: occurrence.frequency for lemma, occurrence in self.terms.items()}

    def is_empty(self) -> bool:
        return not self.terms


class TextAnalyzer:
    """Thread-safe, lazily-initialised wrapper around the spaCy pipeline.

    The model costs ~15 MB of memory and a second to load, so it is loaded once per
    process on first use rather than at import time — which keeps ``/health`` fast and
    lets the API start even if the model is somehow missing.
    """

    def __init__(self, enable_ner: bool = True) -> None:
        self._nlp: Language | None = None
        self._lock = threading.Lock()
        self._enable_ner = enable_ner
        self._keep_pos = frozenset(settings.index.keep_pos_tags)
        self._min_len = settings.index.min_token_length
        self._max_len = settings.index.max_token_length

    # ------------------------------------------------------------------ model ----

    @property
    def nlp(self) -> Language:
        if self._nlp is None:
            with self._lock:
                if self._nlp is None:
                    self._nlp = self._load()
        return self._nlp

    def _load(self) -> Language:
        import spacy

        exclude = list(_EXCLUDED_COMPONENTS)
        if not self._enable_ner:
            exclude.append("ner")

        try:
            nlp = spacy.load(MODEL_NAME, exclude=exclude)
        except OSError as exc:  # pragma: no cover - configuration error
            raise RuntimeError(
                f"spaCy model {MODEL_NAME!r} is not installed. "
                f"Run: python -m spacy download {MODEL_NAME}"
            ) from exc

        # Documents can be long; raise the ceiling but keep it bounded so a pathological
        # page cannot exhaust memory.
        nlp.max_length = 2_000_000
        log.info(
            "nlp_model_loaded",
            model=MODEL_NAME,
            pipeline=list(nlp.pipe_names),
            ner=self._enable_ner,
        )
        return nlp

    def warm(self) -> None:
        """Force model load. Called at worker startup so the first crawl is not slow."""
        self.analyze("warm up the pipeline")

    # ---------------------------------------------------------------- analysis ----

    def _is_index_term(self, token: Any) -> bool:
        """Decide whether a token becomes a dictionary entry.

        Rejects, in order of cheapness: whitespace and punctuation, stop words, tokens
        without a letter, tokens outside the length bounds, and parts of speech that
        carry no topical content (determiners, pronouns, conjunctions, particles).
        """
        if token.is_space or token.is_punct or token.like_url or token.like_email:
            return False
        if token.is_stop:
            return False
        if token.pos_ not in self._keep_pos:
            return False

        lemma = token.lemma_.lower().strip()
        if not (self._min_len <= len(lemma) <= self._max_len):
            return False
        if not _HAS_LETTER.search(lemma):
            return False
        return lemma not in _EXTRA_STOPWORDS

    def _to_image(self, doc: Doc) -> SearchImage:
        terms: dict[str, TermOccurrence] = {}
        ordered: list[str] = []
        position = 0

        for token in doc:
            if not self._is_index_term(token):
                continue
            lemma = token.lemma_.lower().strip()
            occurrence = terms.get(lemma)
            if occurrence is None:
                occurrence = TermOccurrence(lemma=lemma, pos=token.pos_, frequency=0)
                terms[lemma] = occurrence
                ordered.append(lemma)
            occurrence.frequency += 1
            occurrence.positions.append(position)
            position += 1

        entities: list[Entity] = []
        if self._enable_ner and doc.has_annotation("ENT_IOB"):
            seen: set[tuple[str, str]] = set()
            for ent in doc.ents:
                key = (ent.text.strip(), ent.label_)
                if key[0] and key not in seen:
                    seen.add(key)
                    entities.append(Entity(text=key[0], label=key[1]))

        return SearchImage(
            terms=terms,
            token_count=position,
            raw_token_count=len(doc),
            entities=entities[:50],
            ordered_lemmas=ordered,
        )

    def analyze(self, text: str) -> SearchImage:
        """Analyse one text. Used for queries and for single-document indexing."""
        return self._to_image(self.nlp(normalize_whitespace(text)))

    def analyze_document(self, title: str, text: str) -> SearchImage:
        """Analyse a document, normalising its heading first."""
        return self.analyze(compose_document_text(title, text))

    def analyze_query(self, raw: str) -> SearchImage:
        """Analyse a query.

        Applies the same heading normalisation, so a query typed as "Vector Space Model"
        is analysed identically to one typed as "vector space model". This is the same
        pipeline documents go through, which the assignment requires: a query's search
        image and a document's must share one structure within a single system.
        """
        return self.analyze(normalize_heading(raw) if raw else "")

    def analyze_many(self, texts: Iterable[str], batch_size: int = 32) -> Iterator[SearchImage]:
        """Analyse a stream of texts.

        Uses ``nlp.pipe`` rather than a loop over :meth:`analyze` because spaCy batches
        the neural components — for a few hundred documents this is several times faster.
        """
        cleaned = (normalize_whitespace(text) for text in texts)
        for doc in self.nlp.pipe(cleaned, batch_size=batch_size):
            yield self._to_image(doc)


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text or "").strip()


def normalize_heading(heading: str) -> str:
    """Lowercase a Title-Cased heading so that capitalisation does not defeat tagging.

    English lemmatisation is POS-dependent, and spaCy infers part of speech partly from
    capitalisation. In the heading "Evaluating Retrieval Quality" it tags *Evaluating* as
    a proper noun and therefore leaves the lemma as ``evaluating``; in the sentence
    "evaluating the system" the same word is a verb and lemmatises to ``evaluate``. A
    query asking about "evaluated" would then fail to match a document whose title is
    exactly on topic — which is precisely backwards, since titles are among the strongest
    relevance signals a document has.

    Lowercasing the heading restores sentence-like behaviour. All-uppercase short tokens
    are preserved because they are acronyms (``SQL``, ``BM25``, ``TF-IDF``) whose casing
    is meaningful rather than stylistic. Genuine proper nouns are demoted to common nouns,
    which costs nothing here: both are retained as index terms, and lemmas are lowercased
    anyway.

    Headings already written in sentence case are left untouched.
    """
    tokens = (heading or "").split()
    if not tokens:
        return ""

    alphabetic = [token for token in tokens if any(char.isalpha() for char in token)]
    if not alphabetic:
        return heading

    capitalised = sum(1 for token in alphabetic if token[0].isupper())
    if capitalised / len(alphabetic) < 0.6:
        return heading  # already sentence case

    return " ".join(
        token if token.isupper() and 2 <= len(token) <= 6 else token.lower() for token in tokens
    )


def compose_document_text(title: str, text: str) -> str:
    """Join a document's title and body into the single string that gets analysed.

    The normalised title is terminated with a full stop so the tagger treats it as its
    own sentence rather than as the opening fragment of the first paragraph.
    """
    heading = normalize_heading(title).strip().rstrip(".")
    body = (text or "").strip()
    if not heading:
        return body
    return f"{heading}.\n{body}"


def collection_frequencies(images: Iterable[SearchImage]) -> Counter[str]:
    """Total occurrences per lemma across many texts. Used for vocabulary statistics."""
    total: Counter[str] = Counter()
    for image in images:
        for lemma, occurrence in image.terms.items():
            total[lemma] += occurrence.frequency
    return total


#: Process-wide analyzer. Both the API and the crawl worker use this instance so the
#: model is loaded at most once per process.
analyzer = TextAnalyzer()
