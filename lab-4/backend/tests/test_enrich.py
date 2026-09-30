"""Automatic dictionary replenishment (requirement R8)."""

import pytest

from app.mt.morphgen import MorphGenerator
from app.services.enrich import Enricher


@pytest.fixture
def offline(morph: MorphGenerator, monkeypatch) -> Enricher:
    """An enricher with the network source disabled, so only the offline sources answer."""
    enricher = Enricher(morph)
    monkeypatch.setattr("app.services.enrich.settings.enrich_wiktionary_enabled", False)
    return enricher


async def test_derivation_produces_a_real_russian_word(offline: Enricher) -> None:
    suggestion = await offline.suggest("algorithmic", "ADJ")
    assert suggestion.source == "derivation"
    assert suggestion.forms == ["алгоритмический"]
    assert suggestion.confidence >= 0.7
    assert "dictionary" in suggestion.explanation


async def test_derivation_marks_an_unverified_result(offline: Enricher) -> None:
    suggestion = await offline.suggest("tokenizer", "NOUN")
    assert suggestion.forms == ["токенизатор"]
    assert suggestion.confidence < 0.7
    assert "check" in suggestion.explanation


@pytest.mark.parametrize(
    ("english", "russian"),
    [
        ("abstraction", "абстракция"),
        ("discretization", "дискретизация"),
        ("postmodernism", "постмодернизм"),
        ("morphology", "морфология"),
    ],
)
async def test_greco_latin_correspondences(offline: Enricher, english, russian) -> None:
    suggestion = await offline.suggest(english, "NOUN")
    assert suggestion.forms[0] == russian


async def test_derivation_infers_the_part_of_speech(offline: Enricher) -> None:
    assert (await offline.suggest("abstraction", "NOUN")).pos == "n"
    assert (await offline.suggest("algorithmic", "ADJ")).pos == "adj"


async def test_names_fall_back_to_transcription(offline: Enricher) -> None:
    suggestion = await offline.suggest("Vaswani", "PROPN")
    assert suggestion.source == "transcription"
    assert suggestion.forms == ["Васвани"]
    assert suggestion.pos == "pn"


async def test_unrecognisable_word_still_gets_a_proposal(offline: Enricher) -> None:
    suggestion = await offline.suggest("flubber", "NOUN")
    assert suggestion.forms
    assert suggestion.confidence <= 0.4


async def test_a_network_failure_degrades_to_the_offline_sources(
    morph: MorphGenerator, monkeypatch
) -> None:
    enricher = Enricher(morph)

    async def explode(self, lemma: str) -> str:
        raise RuntimeError("no network")

    monkeypatch.setattr(Enricher, "_fetch_wikitext", explode)
    suggestion = await enricher.suggest("abstraction", "NOUN")
    assert suggestion.source == "derivation"
    await enricher.close()


async def test_suggest_many_survives_one_bad_word(offline: Enricher) -> None:
    results = await offline.suggest_many([("abstraction", "NOUN"), ("", "NOUN")])
    assert any(result.forms for result in results)
