"""Requirement R4: every tag the pipeline can emit must have a decoding."""

import pytest

from app.mt.analysis import Analyzer
from app.mt.tagset import (
    OPENCORPORA,
    PENN,
    UPOS,
    explain_features,
    explain_opencorpora,
    explain_penn,
    explain_upos,
)

SAMPLE = """
The neural network model learns representations of words from large corpora, and the
author's narrative remains unclear. Researchers have studied 42 papers; however, they
could not evaluate them all. Who wrote this? "Nobody," she said — isn't that strange?
Turing's paper, published in 1936, changed computing forever: it was not a small change.
The most difficult problems are often the least well-defined ones, e.g. 100% of them.
"""


def test_every_emitted_tag_has_a_decoding(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse(SAMPLE)
    missing_upos = {t.upos for t in analysis.tokens if t.upos not in UPOS}
    missing_penn = {t.tag for t in analysis.tokens if t.tag not in PENN}
    assert not missing_upos, f"universal tags without a decoding: {missing_upos}"
    assert not missing_penn, f"Penn tags without a decoding: {missing_penn}"


def test_every_emitted_feature_has_a_decoding(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse(SAMPLE)
    for token in analysis.tokens:
        decoded = explain_features(token.morph)
        expected = len([item for item in token.morph.split("|") if "=" in item])
        assert len(decoded) == expected
        # An undecoded value falls through as its own lowercased name, which would read as
        # "number: sing" rather than "number: singular".
        for item, phrase in zip(token.morph.split("|"), decoded, strict=False):
            _, _, value = item.partition("=")
            assert phrase.split(": ")[-1] != value or value.islower()


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("VBZ", "verb, 3rd person singular present"),
        ("NNS", "noun, plural"),
        ("JJS", "adjective, superlative"),
        ("POS", "possessive ending"),
        ("DT", "determiner"),
    ],
)
def test_penn_names(tag: str, expected: str) -> None:
    assert explain_penn(tag).name == expected


def test_upos_decoding_mentions_russian_where_relevant() -> None:
    assert "no articles" in explain_upos("DET").description


def test_opencorpora_decoding() -> None:
    decoded = explain_opencorpora("NOUN,inan,femn sing,gent")
    assert decoded == ["noun", "inanimate", "feminine", "singular", "genitive"]


def test_unknown_tag_degrades_without_raising() -> None:
    info = explain_penn("NOT-A-TAG")
    assert info.code == "NOT-A-TAG"
    assert "No decoding" in info.description


def test_opencorpora_covers_pymorphy_output(morph) -> None:
    """Every grammeme pymorphy3 produces for a spread of words must be decodable."""
    words = [
        "сеть",
        "модель",
        "нейронный",
        "изучать",
        "изучен",
        "изучая",
        "быстро",
        "два",
        "он",
        "который",
        "нужно",
        "в",
        "и",
        "не",
        "данные",
        "статья",
        "повествование",
    ]
    unknown: set[str] = set()
    for word in words:
        for parse in morph._parses(word)[:8]:
            for grammeme in str(parse.tag).replace(" ", ",").split(","):
                if grammeme and grammeme not in OPENCORPORA:
                    unknown.add(grammeme)
    assert not unknown, f"pymorphy3 grammemes without a decoding: {unknown}"
