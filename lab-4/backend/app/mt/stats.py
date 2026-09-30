"""Word counts, dictionary coverage and the frequency-ordered word list (tab 1).

The assignment asks for three numbers - words in the input, words translated, and
grammatical information per word - and for a list of the input's words ordered by frequency
of occurrence with their translations and grammatical information. Both come from here.

Frequency is counted over (lemma, part of speech) pairs rather than over surface forms, so
"model" and "models" are one row of the table with a count of two rather than two rows of
one. The surface forms actually seen are kept and shown, because a reader checking the
table against the text needs to find the word as it was written.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.mt.analysis import Analysis
from app.mt.tagset import explain_features, explain_penn, explain_upos


@dataclass(slots=True)
class WordRow:
    """One row of the frequency-ordered word list."""

    lemma: str
    upos: str
    tag: str
    count: int
    forms: list[str]
    translation: str
    translation_accented: str
    gloss: str
    sense_index: int
    sense_count: int
    translated: bool
    pos_name: str
    pos_description: str
    tag_name: str
    tag_description: str
    features: list[str]
    ambiguous: bool = False
    from_user: bool = False
    dropped_by_rule: bool = False
    note: str = ""


@dataclass(slots=True)
class Stats:
    """The numbers the interface shows above the translation."""

    characters: int
    sentences: int
    words: int
    content_words: int
    translated_words: int
    untranslated_words: int
    unique_lemmas: int
    coverage: float
    """Share of content-word tokens that resolved to a dictionary sense."""
    ambiguous_words: int
    dropped_tokens: int
    inserted_tokens: int
    pos_distribution: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "characters": self.characters,
            "sentences": self.sentences,
            "words": self.words,
            "content_words": self.content_words,
            "translated_words": self.translated_words,
            "untranslated_words": self.untranslated_words,
            "unique_lemmas": self.unique_lemmas,
            "coverage": round(self.coverage, 4),
            "ambiguous_words": self.ambiguous_words,
            "dropped_tokens": self.dropped_tokens,
            "inserted_tokens": self.inserted_tokens,
            "pos_distribution": self.pos_distribution,
        }


@dataclass(slots=True)
class TokenTranslation:
    """What the pipeline decided about one source token, for the word list and the tree."""

    sentence: int
    index: int
    text: str
    lemma: str
    upos: str
    tag: str
    morph: str
    dep: str
    head: int
    translation: str = ""
    translation_accented: str = ""
    gloss: str = ""
    sense_index: int = -1
    sense_count: int = 0
    ambiguous: bool = False
    translated: bool = False
    from_user: bool = False
    dropped_by_rule: bool = False
    """Deliberately absent from the output - an article, do-support, the possessive 's."""
    target_tag: str = ""
    target_decoded: list[str] = field(default_factory=list)
    note: str = ""


def build_word_rows(tokens: list[TokenTranslation]) -> list[WordRow]:
    """Aggregate token decisions into the frequency-ordered list of tab 1."""
    groups: dict[tuple[str, str], list[TokenTranslation]] = defaultdict(list)
    for token in tokens:
        if not token.lemma or token.upos in {"PUNCT", "SPACE", "SYM", "X"}:
            continue
        groups[(token.lemma.lower(), token.upos)].append(token)

    rows: list[WordRow] = []
    for (lemma, upos), members in groups.items():
        # The most frequent decision wins the row: the same lemma can resolve to different
        # senses in different sentences, and the table shows the dominant reading.
        best = Counter(
            (m.translation, m.translation_accented, m.gloss, m.sense_index) for m in members
        ).most_common(1)[0][0]
        translation, accented, gloss, sense_index = best
        upos_info = explain_upos(upos)
        tag = Counter(m.tag for m in members).most_common(1)[0][0]
        tag_info = explain_penn(tag)
        morph = Counter(m.morph for m in members).most_common(1)[0][0]
        rows.append(
            WordRow(
                lemma=lemma,
                upos=upos,
                tag=tag,
                count=len(members),
                forms=[form for form, _ in Counter(m.text for m in members).most_common(3)],
                translation=translation,
                translation_accented=accented,
                gloss=gloss,
                sense_index=sense_index,
                sense_count=max(m.sense_count for m in members),
                translated=any(m.translated for m in members),
                pos_name=upos_info.name,
                pos_description=upos_info.description,
                tag_name=tag_info.name,
                tag_description=tag_info.description,
                features=explain_features(morph),
                ambiguous=any(m.ambiguous for m in members),
                from_user=any(m.from_user for m in members),
                dropped_by_rule=all(m.dropped_by_rule for m in members),
                note=next((m.note for m in members if m.note), ""),
            )
        )

    rows.sort(key=lambda row: (-row.count, row.lemma))
    return rows


def compute_stats(
    analysis: Analysis,
    tokens: list[TokenTranslation],
    dropped: int,
    inserted: int,
) -> Stats:
    words = [token for token in analysis.tokens if token.is_word]
    content = [token for token in words if token.is_content]
    translated = [token for token in tokens if token.translated]
    # Coverage measures the dictionary, so the denominator is the words that needed a
    # dictionary. An article or a possessive 's is absent from the Russian on purpose -
    # counting those as failures would understate coverage by ten points and would make the
    # transfer architecture look worse than the word-for-word one, which keeps them.
    lookupable = [
        token
        for token in tokens
        if token.upos not in {"PUNCT", "SPACE", "SYM"} and not token.dropped_by_rule
    ]

    return Stats(
        characters=len(analysis.text),
        sentences=len(analysis.sentences),
        words=len(words),
        content_words=len(content),
        translated_words=len(translated),
        untranslated_words=max(0, len(lookupable) - len(translated)),
        unique_lemmas=len({(t.lemma.lower(), t.upos) for t in lookupable}),
        coverage=(len(translated) / len(lookupable)) if lookupable else 0.0,
        ambiguous_words=sum(1 for token in tokens if token.ambiguous),
        dropped_tokens=dropped,
        inserted_tokens=inserted,
        pos_distribution=dict(Counter(token.upos for token in words).most_common()),
    )
