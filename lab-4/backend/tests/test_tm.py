"""Translation memory: fuzzy matching, post-editing, reuse (additional feature 1)."""

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TmUnit
from app.services import tm


@pytest.fixture(autouse=True)
async def clean(session: AsyncSession):
    await session.execute(delete(TmUnit))
    await session.commit()
    yield
    await session.execute(delete(TmUnit))
    await session.commit()


async def test_exact_match_is_found(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    matches = await tm.search(session, "The model is simple.", "cs")
    assert matches
    assert matches[0].exact
    assert matches[0].target_text == "Модель проста."


async def test_punctuation_and_case_do_not_matter(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    matches = await tm.search(session, "the model is simple", "cs")
    assert matches and matches[0].exact


async def test_near_miss_is_a_fuzzy_match(session: AsyncSession) -> None:
    await tm.remember(session, "The neural network model is simple.", "Модель проста.", "cs")
    matches = await tm.search(session, "The neural network model is complex.", "cs")
    assert matches
    assert not matches[0].exact
    assert 0.7 <= matches[0].similarity < 0.98


async def test_unrelated_sentence_does_not_match(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    assert await tm.search(session, "Critics argued about the final scene.", "cs") == []


async def test_the_requested_domain_wins_a_tie(session: AsyncSession) -> None:
    await tm.remember(session, "The character is unclear.", "Символ неясен.", "cs")
    await tm.remember(session, "The character is unclear.", "Персонаж неясен.", "lit")
    literary = await tm.search(session, "The character is unclear.", "lit")
    technical = await tm.search(session, "The character is unclear.", "cs")
    assert literary[0].target_text == "Персонаж неясен."
    assert technical[0].target_text == "Символ неясен."


async def test_post_editing_replaces_the_stored_translation(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель простая.", "cs")
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    total, units = await tm.page(session)
    assert total == 1
    assert units[0].target_text == "Модель проста."


async def test_reuse_is_counted(session: AsyncSession) -> None:
    unit = await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    await tm.count_hit(session, unit.id)
    await tm.count_hit(session, unit.id)
    statistics = await tm.stats(session)
    assert statistics["total_hits"] == 2


async def test_best_matches_are_keyed_by_sentence_position(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    matches = await tm.best_matches(
        session, ["Something else entirely.", "The model is simple."], "cs"
    )
    assert set(matches) == {1}


async def test_deleting_a_unit(session: AsyncSession) -> None:
    unit = await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    assert await tm.forget(session, unit.id)
    assert not await tm.forget(session, unit.id)


async def test_stats_split_by_origin_and_domain(session: AsyncSession) -> None:
    await tm.remember(session, "One sentence here.", "Одно.", "cs", origin="post-edit")
    await tm.remember(session, "Another sentence here.", "Другое.", "lit", origin="import")
    statistics = await tm.stats(session)
    assert statistics["post_edited"] == 1
    assert statistics["imported"] == 1
    assert statistics["by_domain"] == {"cs": 1, "lit": 1}


async def test_browsing_can_be_filtered(session: AsyncSession) -> None:
    await tm.remember(session, "The model is simple.", "Модель проста.", "cs")
    await tm.remember(session, "The narrator is unreliable.", "Рассказчик ненадёжен.", "lit")
    total, units = await tm.page(session, query="narrator")
    assert total == 1
    assert units[0].domain_code == "lit"
