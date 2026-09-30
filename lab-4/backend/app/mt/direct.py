"""The direct translation architecture - «системы прямого перевода».

The methodology's first class of machine-translation system: "the source text is gradually
turned into text in the target language by replacing all of its elements found in the
dictionary with their translation equivalents. No translation model is used". Only local
context matters, which in practice means none at all.

It is implemented here in full, and it is not a straw man - it is the baseline the transfer
architecture has to beat, and the architecture comparison shows exactly where it fails:
no case endings, no agreement, articles and auxiliaries left in place, "of" translated as
a word, and the first dictionary sense taken every time - which is how «computer» becomes
«вычислитель».
"""

from __future__ import annotations

from app.mt.analysis import Sentence
from app.mt.lexicon import LexiconIndex, Unit, token_keys
from app.mt.pieces import Kind, Piece, SentenceTranslation, detokenise


def translate_direct(
    sentence: Sentence, units: list[Unit], index: LexiconIndex
) -> SentenceTranslation:
    pieces: list[Piece] = []

    for unit in units:
        head = unit.tokens[0]
        source_text = "".join(t.text + t.whitespace for t in unit.tokens).strip()
        source_indices = tuple(t.index for t in unit.tokens)

        if head.is_punct:
            pieces.append(
                Piece(
                    surface=head.text,
                    kind=Kind.PUNCT,
                    source_indices=source_indices,
                    source_text=source_text,
                )
            )
            continue

        equivalent = _first_equivalent(unit, index)
        if equivalent is None:
            pieces.append(
                Piece(
                    surface=source_text,
                    kind=Kind.UNTRANSLATED,
                    source_indices=source_indices,
                    source_text=source_text,
                    note="not found in the dictionary",
                )
            )
            continue

        lemma, gloss = equivalent
        pieces.append(
            Piece(
                surface=lemma,
                kind=Kind.WORD,
                source_indices=source_indices,
                source_text=source_text,
                lemma=lemma,
                note=gloss[:80],
            )
        )

    target = detokenise(pieces)
    return SentenceTranslation(
        index=sentence.index,
        source=sentence.text,
        target=target,
        pieces=pieces,
        stages={"word-for-word substitution": target},
    )


def _first_equivalent(unit: Unit, index: LexiconIndex) -> tuple[str, str] | None:
    """The dictionary's first equivalent, with no disambiguation of any kind."""
    keys = [unit.key] if unit.key else []
    if unit.size == 1:
        keys.extend(token_keys(unit.tokens[0]))

    for key in keys:
        if not key:
            continue
        # Deliberately ignores the part of speech: a direct system substitutes whatever the
        # dictionary lists first, which is one of the reasons its output reads badly.
        for entry in index.get(key):
            for sense in entry.senses:
                if sense.translations:
                    return sense.translations[0].plain, sense.gloss
    return None
