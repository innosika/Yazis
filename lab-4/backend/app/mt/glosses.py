"""Parsing of dictionary glosses.

A gloss from the source dictionary looks like this:

    (now, rare, chiefly, historical) A person employed to perform computations.
    (computing, Internet) A computer network: multiple computers linked together.

The leading parenthesis is Wiktionary's label block. Splitting it off gives two things the
disambiguator needs: the label list, and a definition clean enough to compare against the
context of the word being translated.
"""

import re

from app.mt.domains import REGIONAL_LABELS, STRUCTURAL_LABELS

_LABEL_BLOCK = re.compile(r"^\s*\(([^()]{0,200}?)\)\s*")
_WORD = re.compile(r"[a-z][a-z'-]{2,}")

# Definitions are written in an English that is itself mostly function words. Removing them
# keeps the Lesk overlap and the keyword profile measuring content rather than grammar.
_STOPWORDS = frozenset(
    """
    a an the and or but nor for yet so of to in on at by with from into onto upon about
    over under above below between among through during before after since until while
    that which who whom whose what where when why how this these those there here
    is are was were be been being am do does did done have has had having will would
    shall should can could may might must not no nor as if then than such other another
    any some each every all both few more most many much less least own same very
    one two three four five six seven eight nine ten first second etc used using use
    something someone anything anyone nothing person thing things especially usually
    often sometimes generally typically particularly specifically e g i e ie eg cf
    also esp its it he she they them his her their our your my me we you i
    """.split()
)


def parse_labels(gloss: str) -> tuple[list[str], str]:
    """Split a gloss into its label list and its definition text.

    Structural labels (`transitive`, `countable`) and regional labels (`US`, `UK`) are
    dropped: they are real lexicographic information but carry no signal about which sense
    a computer-science paper means.
    """
    match = _LABEL_BLOCK.match(gloss or "")
    if not match:
        return [], (gloss or "").strip()

    raw = match.group(1)
    labels: list[str] = []
    for part in raw.split(","):
        label = part.strip().strip("_").strip().lower()
        if not label or label in STRUCTURAL_LABELS or label in REGIONAL_LABELS:
            continue
        labels.append(label)
    return labels, gloss[match.end() :].strip()


def content_words(text: str) -> set[str]:
    """Content lemmas of a definition, approximated without loading a tagger.

    Seeding touches 78 720 glosses; running a statistical lemmatiser over all of them would
    add minutes to `make up` for a gain the keyword profile cannot measure. Plural and
    gerund stripping is enough to make "networks", "network" and "networking" collide.
    """
    words: set[str] = set()
    for token in _WORD.findall((text or "").lower()):
        if token in _STOPWORDS:
            continue
        words.add(token)
        words.add(_singularise(token))
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _singularise(word: str) -> str:
    for suffix, replacement in (
        ("ies", "y"),
        ("sses", "ss"),
        ("shes", "sh"),
        ("ches", "ch"),
        ("xes", "x"),
        ("ing", ""),
        ("s", ""),
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)] + replacement
    return word
