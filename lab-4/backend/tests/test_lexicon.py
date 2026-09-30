"""Dictionary lookup: part-of-speech compatibility and multiword units."""

from app.mt.analysis import Analyzer
from app.mt.lexicon import (
    POS_COMPATIBILITY,
    candidate_keys,
    segment_units,
    span_keys,
    token_keys,
)
from tests import factories


def test_token_keys_try_the_lemma_first(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The models learn.")
    models = next(token for token in analysis.tokens if token.text == "models")
    assert token_keys(models)[0] == "model"
    assert "models" in token_keys(models)


def test_hyphenated_span_rejoins_into_one_key(analyzer: Analyzer) -> None:
    """spaCy splits "rule-based" into three tokens; the key must be the hyphenated word."""
    analysis = analyzer.analyse("A rule-based system.")
    tokens = analysis.sentences[0].tokens
    span = [t for t in tokens if t.text in {"rule", "-", "based"}]
    assert "rule-based" in span_keys(span)


def test_long_hyphenated_headword_is_reachable(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("State-of-the-art results.")
    assert "state-of-the-art" in candidate_keys(analysis)


def test_candidate_keys_include_ngrams(analyzer: Analyzer) -> None:
    analysis = analyzer.analyse("The machine learning system works.")
    keys = candidate_keys(analysis)
    assert "machine learning" in keys
    assert "machine learning system" in keys


def test_lookup_prefers_the_matching_part_of_speech() -> None:
    index = factories.index(
        factories.entry("study", "n", ("A room for reading.", ["кабинет"])),
        factories.entry("study", "v", ("To examine closely.", ["изучать"])),
    )
    verbs = index.get("study", "VERB")
    assert verbs[0].pos == "v"
    nouns = index.get("study", "NOUN")
    assert nouns[0].pos == "n"


def test_incompatible_entries_are_demoted_not_dropped() -> None:
    """A wrong-part-of-speech reading beats leaving the word in English."""
    index = factories.index(factories.entry("paper", "adj", ("Made of paper.", ["бумажный"])))
    results = index.get("paper", "NOUN")
    assert len(results) == 1
    assert not index.matches("paper", "NOUN")


def test_multiword_unit_wins_over_single_words(analyzer: Analyzer) -> None:
    index = factories.index(
        factories.entry("machine learning", "n", ("(computing) …", ["машинное обучение"])),
        factories.entry("machine", "n", ("A device.", ["машина"])),
        factories.entry("learning", "n", ("Acquisition of knowledge.", ["учение"])),
        factories.entry("system", "n", ("A whole.", ["система"])),
    )
    analysis = analyzer.analyse("The machine learning system works.")
    units = segment_units(analysis.sentences[0], index)
    keys = [unit.key for unit in units]
    assert "machine learning" in keys
    assert "machine" not in keys


def test_punctuation_is_never_glued_into_a_unit(analyzer: Analyzer) -> None:
    index = factories.index(factories.entry("machine learning", "n", ("…", ["машинное обучение"])))
    analysis = analyzer.analyse("Machine, learning.")
    units = segment_units(analysis.sentences[0], index)
    assert all(unit.size == 1 for unit in units)


def test_every_universal_tag_has_a_compatibility_entry(analyzer: Analyzer) -> None:
    text = "Researchers have studied 42 papers; however, they could not evaluate them all!"
    analysis = analyzer.analyse(text)
    for token in analysis.tokens:
        if token.is_punct or token.is_space:
            continue
        assert token.upos in POS_COMPATIBILITY, f"{token.upos} has no compatibility mapping"
