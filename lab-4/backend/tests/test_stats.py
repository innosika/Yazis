"""Word counts, dictionary coverage and the frequency-ordered list (requirements R2, R3, R6)."""

from app.mt.domains import get_domain
from app.mt.pipeline import Pipeline
from tests.test_transfer import DICTIONARY


def test_word_count_matches_the_input(pipeline: Pipeline) -> None:
    result = pipeline.run(
        "The model is simple. The system is simple.", DICTIONARY, get_domain("cs")
    )
    assert result.stats.words == 8
    assert result.stats.sentences == 2
    assert result.stats.characters == len(result.source)


def test_translated_count_counts_resolved_words(pipeline: Pipeline) -> None:
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    assert result.stats.translated_words >= 2
    assert result.stats.translated_words <= result.stats.words


def test_coverage_excludes_deliberately_dropped_words(pipeline: Pipeline) -> None:
    """An article is absent from the Russian on purpose, so it is not a coverage failure."""
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    assert result.stats.dropped_tokens >= 1
    assert result.stats.coverage == 1.0


def test_untranslated_words_are_counted(pipeline: Pipeline) -> None:
    result = pipeline.run("The tokenizer is simple.", DICTIONARY, get_domain("cs"))
    assert result.stats.untranslated_words == 1
    assert result.stats.coverage < 1.0


def test_frequency_list_is_ordered_by_count(pipeline: Pipeline) -> None:
    text = "The model is simple. The model is simple. The system is simple."
    result = pipeline.run(text, DICTIONARY, get_domain("cs"))
    counts = [row.count for row in result.words]
    assert counts == sorted(counts, reverse=True)
    assert result.words[0].count == 3


def test_frequency_list_merges_inflected_forms(pipeline: Pipeline) -> None:
    result = pipeline.run("The model and the models.", DICTIONARY, get_domain("cs"))
    model = next(row for row in result.words if row.lemma == "model")
    assert model.count == 2
    assert set(model.forms) == {"model", "models"}


def test_every_row_carries_grammatical_information(pipeline: Pipeline) -> None:
    result = pipeline.run(
        "Researchers evaluated the quality of the models.", DICTIONARY, get_domain("cs")
    )
    assert result.words
    for row in result.words:
        assert row.tag and row.tag_name and row.tag_description
        assert row.upos and row.pos_name and row.pos_description


def test_dropped_rows_report_the_reason_not_a_translation(pipeline: Pipeline) -> None:
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    article = next(row for row in result.words if row.lemma == "the")
    assert article.dropped_by_rule
    assert article.translation == ""
    assert "articles" in article.note


def test_pos_distribution_is_reported(pipeline: Pipeline) -> None:
    result = pipeline.run("The model is simple.", DICTIONARY, get_domain("cs"))
    assert result.stats.pos_distribution.get("NOUN", 0) >= 1


def test_oov_words_are_collected_once_with_a_count(pipeline: Pipeline) -> None:
    text = "The tokenizer is simple. The tokenizer is simple."
    result = pipeline.run(text, DICTIONARY, get_domain("cs"))
    assert len(result.oov) == 1
    assert result.oov[0].lemma == "tokenizer"
    assert result.oov[0].occurrences == 2


def test_proper_nouns_are_not_queued_as_dictionary_gaps(pipeline: Pipeline) -> None:
    """A name is transcribed, not missing - queueing it would fill the list with noise."""
    result = pipeline.run("The model of Vaswani is simple.", DICTIONARY, get_domain("cs"))
    assert all(mention.lemma != "vaswani" for mention in result.oov)
