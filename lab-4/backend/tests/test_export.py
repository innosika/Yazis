"""Unicode `.txt` export (requirement R9)."""

from app.mt.domains import get_domain
from app.mt.pipeline import Pipeline
from app.services import export
from tests.test_transfer import DICTIONARY

TEXT = (
    "The neural network model is simple. Researchers evaluate the quality of the model "
    "with data. The tokenizer is simple."
)


def _report(pipeline: Pipeline) -> str:
    result = pipeline.run(TEXT, DICTIONARY, get_domain("cs"), include_direct=True)
    return export.build_txt(result, title="Test document")


def test_file_starts_with_a_byte_order_mark(pipeline: Pipeline) -> None:
    assert _report(pipeline).startswith("﻿")


def test_content_is_valid_utf8(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    assert content.encode("utf-8").decode("utf-8") == content


def test_report_contains_every_required_section(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    for heading in (
        "STATISTICS",
        "TRANSLATION",
        "WORDS BY FREQUENCY OF OCCURRENCE",
        "PART-OF-SPEECH TAG DECODING",
        "WORDS NOT FOUND IN THE DICTIONARY",
    ):
        assert heading in content, f"missing section: {heading}"


def test_statistics_are_present(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    assert "Words in the input text" in content
    assert "Words translated" in content
    assert "Dictionary coverage" in content


def test_word_list_carries_translations_and_grammar(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    assert "модель" in content
    assert "noun, singular or mass" in content


def test_untranslated_words_are_marked_not_silently_blank(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    assert "not in dictionary" in content
    assert "tokenizer" in content


def test_dropped_words_are_marked(pipeline: Pipeline) -> None:
    assert "(dropped)" in _report(pipeline)


def test_direct_translation_is_included_for_comparison(pipeline: Pipeline) -> None:
    assert "WORD-FOR-WORD TRANSLATION" in _report(pipeline)


def test_credits_name_the_data_sources(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    assert "FreeDict" in content
    assert "spaCy" in content
    assert "pymorphy3" in content


def test_filename_is_safe_and_timestamped() -> None:
    name = export.safe_filename("Тест / документ №1")
    assert name.endswith(".txt")
    assert "/" not in name
    assert len(name) > 10


def test_saved_file_round_trips(pipeline: Pipeline) -> None:
    content = _report(pipeline)
    path = export.save_txt(content, export.safe_filename("round-trip"))
    try:
        assert path.read_text(encoding="utf-8") == content
    finally:
        path.unlink(missing_ok=True)
