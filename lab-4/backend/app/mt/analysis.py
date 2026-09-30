"""Stage 1 of the pipeline: analysis of the English input.

This is the «анализ» half of a transfer system. Nothing here knows anything about Russian:
it turns a string into sentences, tokens, lemmas, part-of-speech tags, morphological
features and a dependency tree, and every later stage reads only this structure.

spaCy's `en_core_web_md` does the work. The medium model rather than the small one for two
reasons: it tags noun phrases such as "large corpora" correctly where the small model
guesses a proper noun, and it ships 300-dimensional word vectors, which the disambiguator
uses as its weakest-but-broadest signal.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cost avoided at runtime
    import numpy as np
    from spacy.language import Language

from app.config import settings

log = logging.getLogger(__name__)

_HAS_ALNUM = re.compile(r"\w", re.UNICODE)


@dataclass(frozen=True, slots=True)
class Token:
    """One analysed English token."""

    index: int
    """Position inside its sentence."""
    text: str
    whitespace: str
    """Whitespace that followed the token in the source, so the input can be rebuilt exactly."""
    lemma: str
    upos: str
    tag: str
    """Penn Treebank tag - where English tense, number and degree actually live."""
    morph: str
    dep: str
    head: int
    """Index of the syntactic head inside the sentence; equal to `index` for the root."""
    ent_type: str
    is_stop: bool
    is_punct: bool
    is_space: bool
    is_title: bool
    is_upper: bool
    start_char: int
    end_char: int

    @property
    def is_word(self) -> bool:
        """Whether this token counts towards «количество слов во входном тексте»."""
        return not self.is_punct and not self.is_space and bool(_HAS_ALNUM.search(self.text))

    @property
    def is_content(self) -> bool:
        """Whether the token carries lexical meaning worth looking up in a dictionary."""
        return self.upos in {"NOUN", "PROPN", "VERB", "ADJ", "ADV", "NUM"}

    @property
    def is_root(self) -> bool:
        return self.head == self.index


@dataclass(frozen=True, slots=True)
class Sentence:
    index: int
    text: str
    start_char: int
    end_char: int
    tokens: tuple[Token, ...]

    @property
    def root(self) -> Token | None:
        for token in self.tokens:
            if token.is_root and not token.is_punct:
                return token
        return self.tokens[0] if self.tokens else None

    def children(self, token: Token) -> list[Token]:
        return [t for t in self.tokens if t.head == token.index and t.index != token.index]

    def head_of(self, token: Token) -> Token | None:
        return None if token.is_root else self.tokens[token.head]


@dataclass(frozen=True, slots=True)
class Analysis:
    text: str
    sentences: tuple[Sentence, ...]

    @property
    def tokens(self) -> list[Token]:
        return [token for sentence in self.sentences for token in sentence.tokens]

    @property
    def word_count(self) -> int:
        return sum(1 for token in self.tokens if token.is_word)


class Analyzer:
    """Wraps the spaCy pipeline. One instance per process, created during app startup."""

    def __init__(self, model: str | None = None) -> None:
        import spacy

        self.model_name = model or settings.spacy_model
        log.info("loading spaCy model %s", self.model_name)
        self._nlp: Language = spacy.load(self.model_name)
        self._has_vectors = bool(self._nlp.vocab.vectors.shape[0])
        log.info("spaCy %s ready, vectors=%s", self.model_name, self._nlp.vocab.vectors.shape)

    @property
    def nlp(self) -> Language:
        return self._nlp

    @property
    def has_vectors(self) -> bool:
        return self._has_vectors

    def analyse(self, text: str) -> Analysis:
        doc = self._nlp(text)
        sentences: list[Sentence] = []
        for sentence_index, span in enumerate(doc.sents):
            offset = span.start
            tokens = tuple(
                Token(
                    index=token.i - offset,
                    text=token.text,
                    whitespace=token.whitespace_,
                    lemma=token.lemma_,
                    upos=token.pos_,
                    tag=token.tag_,
                    morph=str(token.morph),
                    dep=token.dep_,
                    # spaCy links a sentence root to itself, which is exactly the
                    # convention `Token.is_root` relies on. Heads never cross sentence
                    # boundaries, so clamping is a guard, not a behaviour.
                    head=min(max(token.head.i - offset, 0), len(span) - 1),
                    ent_type=token.ent_type_,
                    is_stop=token.is_stop,
                    is_punct=token.is_punct,
                    is_space=token.is_space,
                    is_title=token.text.istitle(),
                    is_upper=token.text.isupper() and len(token.text) > 1,
                    start_char=token.idx,
                    end_char=token.idx + len(token.text),
                )
                for token in span
            )
            if not any(token.is_word for token in tokens):
                continue
            sentences.append(
                Sentence(
                    index=sentence_index,
                    text=span.text,
                    start_char=span.start_char,
                    end_char=span.end_char,
                    tokens=tokens,
                )
            )
        # Re-index so the numbering has no gaps after empty sentences were dropped.
        sentences = [
            Sentence(i, s.text, s.start_char, s.end_char, s.tokens) for i, s in enumerate(sentences)
        ]
        return Analysis(text=text, sentences=tuple(sentences))

    @lru_cache(maxsize=50_000)  # noqa: B019 - one Analyzer per process, bounded by design
    def vector(self, word: str) -> np.ndarray | None:
        """Vector of a single word, looked up in the vocabulary without running the pipeline.

        The disambiguator compares hundreds of gloss words per sentence; going through the
        full pipeline for each would cost more than every other stage combined.
        """
        if not self._has_vectors:
            return None
        lexeme = self._nlp.vocab[word]
        if not lexeme.has_vector:
            return None
        import numpy as np

        # spaCy returns a thinc array; numpy's own stubs only accept an ndarray, and the
        # conversion is free because the buffer is shared.
        vector = np.asarray(lexeme.vector, dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else None
