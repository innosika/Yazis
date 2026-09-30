"""Contract tests for every route, against the real application and database."""

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DictEntry, OovTerm, SenseOverride, TmUnit

CS_TEXT = "The neural network model learns representations of words from large corpora."
LIT_TEXT = "The main character of the novel is an unreliable narrator."


@pytest.fixture(autouse=True)
async def clean(session: AsyncSession):
    """Remove only what the tests create; the seeded dictionary is left alone."""
    yield
    await session.execute(delete(SenseOverride))
    await session.execute(delete(TmUnit))
    await session.execute(delete(OovTerm))
    await session.execute(delete(DictEntry).where(DictEntry.is_user.is_(True)))
    await session.commit()


# ------------------------------------------------------------------------------ health


async def test_readiness_reports_the_dictionary_size(client) -> None:
    response = await client.get("/api/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dictionary_entries"] > 60_000


async def test_liveness(client) -> None:
    assert (await client.get("/api/health/live")).json() == {"status": "live"}


# ------------------------------------------------------------------------- translation


async def test_translate_returns_every_required_section(client) -> None:
    response = await client.post(
        "/api/translate", json={"text": CS_TEXT, "domain": "cs", "mode": "transfer"}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["target"]
    assert body["stats"]["words"] > 0
    assert body["stats"]["translated_words"] > 0
    assert 0 <= body["stats"]["coverage"] <= 1
    assert len(body["sentences"]) == 1
    assert body["words"], "tab 1: the frequency-ordered word list"
    assert body["trees"][0]["root"], "tab 2: the parse tree"
    assert body["document_id"]


async def test_translate_word_rows_carry_tag_decoding(client) -> None:
    body = (await client.post("/api/translate", json={"text": CS_TEXT, "domain": "cs"})).json()
    for row in body["words"]:
        assert row["tag_name"] and row["tag_description"]
        assert row["pos_name"] and row["pos_description"]


async def test_translate_includes_the_word_for_word_baseline(client) -> None:
    body = (
        await client.post(
            "/api/translate", json={"text": CS_TEXT, "domain": "cs", "include_direct": True}
        )
    ).json()
    assert body["direct_target"]
    assert body["direct_target"] != body["target"]


async def test_domain_changes_the_translation(client) -> None:
    payload = {"text": LIT_TEXT, "mode": "transfer"}
    literary = (await client.post("/api/translate", json={**payload, "domain": "lit"})).json()
    technical = (await client.post("/api/translate", json={**payload, "domain": "cs"})).json()
    assert "персонаж" in literary["target"]
    assert "персонаж" not in technical["target"]


async def test_ambiguities_expose_their_score_breakdown(client) -> None:
    body = (await client.post("/api/translate", json={"text": LIT_TEXT, "domain": "lit"})).json()
    assert body["ambiguities"]
    candidate = body["ambiguities"][0]["candidates"][0]
    assert candidate["signals"]
    assert all({"name", "contribution", "detail"} <= set(s) for s in candidate["signals"])


async def test_unknown_domain_is_rejected(client) -> None:
    response = await client.post("/api/translate", json={"text": CS_TEXT, "domain": "nope"})
    assert response.status_code == 422


async def test_empty_text_is_rejected(client) -> None:
    assert (await client.post("/api/translate", json={"text": ""})).status_code == 422


async def test_samples_are_offered_with_their_domain(client) -> None:
    body = (await client.get("/api/translate/samples")).json()
    assert len(body) >= 2
    assert {sample["domain"] for sample in body} <= {"cs", "lit", "general"}
    assert all(sample["text"] for sample in body)


# --------------------------------------------------------------------------- reference


async def test_meta_describes_the_system(client) -> None:
    body = (await client.get("/api/meta")).json()
    assert body["direction"] == {"source": "English", "target": "Russian", "code": "en-ru"}
    assert {domain["code"] for domain in body["domains"]} == {"general", "cs", "lit"}
    assert body["dictionary"]["entries"] > 60_000
    assert body["dictionary"]["multiword_units"] > 1_000


async def test_tagsets_are_complete(client) -> None:
    body = (await client.get("/api/meta/tagsets")).json()
    assert len(body["upos"]) >= 17
    assert len(body["penn"]) >= 36
    assert len(body["opencorpora"]) >= 40
    assert len(body["dependencies"]) >= 30


async def test_rules_are_exposed_as_data(client) -> None:
    body = (await client.get("/api/meta/rules")).json()
    of_rule = next(item for item in body["prepositions"] if item["english"] == "of")
    assert of_rule["case"] == "gen"
    assert body["register_penalties"][0]["penalty"] == 1.0


# -------------------------------------------------------------------------- dictionary


async def test_dictionary_search(client) -> None:
    body = (await client.get("/api/dictionary/entries", params={"q": "network"})).json()
    assert body["total"] >= 1
    entry = body["items"][0]
    assert entry["senses"]
    assert entry["senses"][0]["translations"]


async def test_create_correct_and_delete_an_entry(client) -> None:
    created = await client.post(
        "/api/dictionary/entries",
        json={
            "headword": "tokenizer",
            "pos": "n",
            "senses": [
                {
                    "gloss": "(computing) A program that splits text into tokens.",
                    "translations": ["токенизатор"],
                }
            ],
        },
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["is_user"]
    assert entry["senses"][0]["labels"] == ["computing"]
    assert entry["senses"][0]["domain_scores"].get("cs")

    sense_id = entry["senses"][0]["id"]
    corrected = await client.put(
        f"/api/dictionary/senses/{sense_id}/translations",
        json={"forms": ["токенизатор", "разбиватель на токены"]},
    )
    assert corrected.status_code == 200
    forms = [t["form_plain"] for t in corrected.json()["senses"][0]["translations"]]
    assert forms == ["токенизатор", "разбиватель на токены"]

    assert (await client.delete(f"/api/dictionary/entries/{entry['id']}")).status_code == 204
    assert (await client.get(f"/api/dictionary/entries/{entry['id']}")).status_code == 404


async def test_a_new_entry_is_used_by_the_next_translation(client) -> None:
    """The point of the utility: accepting a word closes the gap."""
    before = (
        await client.post(
            "/api/translate", json={"text": "The tokenizer is simple.", "domain": "cs"}
        )
    ).json()
    assert any(item["lemma"] == "tokenizer" for item in before["oov"])

    await client.post(
        "/api/dictionary/entries",
        json={
            "headword": "tokenizer",
            "pos": "n",
            "senses": [{"gloss": "(computing) …", "translations": ["токенизатор"]}],
        },
    )

    after = (
        await client.post(
            "/api/translate", json={"text": "The tokenizer is simple.", "domain": "cs"}
        )
    ).json()
    assert not any(item["lemma"] == "tokenizer" for item in after["oov"])
    assert "токенизатор" in after["target"].lower()


async def test_suggestion_endpoint(client) -> None:
    body = (
        await client.get("/api/dictionary/suggest", params={"lemma": "abstraction", "upos": "NOUN"})
    ).json()
    assert body["forms"]
    assert body["source"] in {"wiktionary", "derivation", "transcription"}
    assert body["explanation"]


async def test_scan_queues_unknown_words_and_proposes_translations(client) -> None:
    body = (
        await client.post(
            "/api/dictionary/scan",
            json={"text": "The tokenizer and the discretization are simple.", "domain": "cs"},
        )
    ).json()
    assert body["found"] >= 1
    assert body["suggestions"]

    queue = (await client.get("/api/dictionary/oov")).json()
    assert any(item["lemma"] == "tokenizer" for item in queue["items"])


async def test_accepting_a_queued_word_creates_an_entry(client) -> None:
    await client.post("/api/dictionary/scan", json={"text": "The tokenizer is simple."})
    queue = (await client.get("/api/dictionary/oov")).json()
    term = next(item for item in queue["items"] if item["lemma"] == "tokenizer")

    created = await client.post(
        f"/api/dictionary/oov/{term['id']}/accept", json={"forms": ["токенизатор"]}
    )
    assert created.status_code == 200
    assert created.json()["headword_norm"] == "tokenizer"
    assert (await client.get("/api/dictionary/oov")).json()["items"] == [] or all(
        item["lemma"] != "tokenizer"
        for item in (await client.get("/api/dictionary/oov")).json()["items"]
    )


async def test_dismissing_a_queued_word(client) -> None:
    await client.post("/api/dictionary/scan", json={"text": "The tokenizer is simple."})
    queue = (await client.get("/api/dictionary/oov")).json()
    term = next(item for item in queue["items"] if item["lemma"] == "tokenizer")
    assert (await client.post(f"/api/dictionary/oov/{term['id']}/dismiss")).status_code == 204


# ---------------------------------------------------------------------- sense locking


async def test_locking_a_sense_changes_the_translation(client) -> None:
    """Additional feature 2: the user's choice overrides every signal."""
    body = (await client.post("/api/translate", json={"text": LIT_TEXT, "domain": "lit"})).json()
    ambiguity = next(item for item in body["ambiguities"] if item["lemma"] == "character")
    chosen = next(c for c in ambiguity["candidates"] if c["selected"])
    other = next(c for c in ambiguity["candidates"] if not c["selected"])

    assert (
        await client.post(
            "/api/dictionary/overrides",
            json={
                "headword": "character",
                "pos": "n",
                "domain_code": "lit",
                "sense_id": other["sense_id"],
                "translation_id": other["translation_id"],
            },
        )
    ).status_code == 204

    after = (await client.post("/api/translate", json={"text": LIT_TEXT, "domain": "lit"})).json()
    assert other["translation"] != chosen["translation"]
    assert other["translation"] in after["target"] or not after["ambiguities"]

    overrides = (await client.get("/api/dictionary/overrides")).json()
    assert overrides and overrides[0]["headword_norm"] == "character"
    assert (
        await client.delete(f"/api/dictionary/overrides/{overrides[0]['id']}")
    ).status_code == 204


# --------------------------------------------------------------------- memory feature


async def test_post_edit_is_stored_and_reused(client) -> None:
    """Additional feature 1, end to end."""
    first = (await client.post("/api/translate", json={"text": LIT_TEXT, "domain": "lit"})).json()
    machine = first["sentences"][0]["target"]

    saved = await client.post(
        "/api/memory/units",
        json={
            "source_text": LIT_TEXT,
            "target_text": "Главный герой романа — ненадёжный рассказчик.",
            "domain_code": "lit",
        },
    )
    assert saved.status_code == 201

    again = (await client.post("/api/translate", json={"text": LIT_TEXT, "domain": "lit"})).json()
    assert again["memory_hits"] == 1
    assert again["sentences"][0]["memory"]["exact"]
    assert again["sentences"][0]["target"] == "Главный герой романа — ненадёжный рассказчик."
    assert again["target"] != machine


async def test_fuzzy_match_is_reported_but_not_applied(client) -> None:
    await client.post(
        "/api/memory/units",
        json={
            "source_text": "The main character of the novel is an unreliable narrator.",
            "target_text": "Главный герой романа — ненадёжный рассказчик.",
            "domain_code": "lit",
        },
    )
    variant = "The main character of the book is an unreliable narrator."
    body = (await client.post("/api/translate", json={"text": variant, "domain": "lit"})).json()
    match = body["sentences"][0]["memory"]
    assert match is not None
    assert not match["exact"]
    assert 0.7 <= match["similarity"] < 0.98
    assert body["sentences"][0]["target"] != match["target_text"]


async def test_memory_search_browse_and_stats(client) -> None:
    await client.post(
        "/api/memory/units",
        json={"source_text": LIT_TEXT, "target_text": "Перевод.", "domain_code": "lit"},
    )
    matches = (
        await client.post("/api/memory/search", json={"text": LIT_TEXT, "domain": "lit"})
    ).json()
    assert matches and matches[0]["exact"]

    listing = (await client.get("/api/memory/units")).json()
    assert listing["total"] == 1

    statistics = (await client.get("/api/memory/stats")).json()
    assert statistics["units"] == 1
    assert statistics["post_edited"] == 1

    unit_id = listing["items"][0]["id"]
    assert (await client.delete(f"/api/memory/units/{unit_id}")).status_code == 204


async def test_memory_import_and_export(client) -> None:
    imported = await client.post(
        "/api/memory/import",
        json={
            "units": [
                {"source_text": "One sentence.", "target_text": "Одно предложение."},
                {"source_text": "Another sentence.", "target_text": "Другое предложение."},
            ]
        },
    )
    assert imported.status_code == 200
    assert imported.json()["imported"] == 2

    exported = (await client.get("/api/memory/export")).json()
    assert len(exported) == 2


# ------------------------------------------------------------------------------ export


async def test_txt_export_is_a_unicode_download(client) -> None:
    response = await client.post(
        "/api/export/txt", json={"text": CS_TEXT, "domain": "cs", "mode": "transfer"}
    )
    assert response.status_code == 200
    assert "charset=utf-8" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.startswith("﻿")
    assert "WORDS BY FREQUENCY OF OCCURRENCE" in response.text


async def test_documents_are_recorded_and_reopenable(client) -> None:
    created = (
        await client.post(
            "/api/translate", json={"text": CS_TEXT, "domain": "cs", "title": "Paper"}
        )
    ).json()
    listing = (await client.get("/api/export/documents")).json()
    assert any(item["id"] == created["document_id"] for item in listing)

    reopened = (await client.get(f"/api/export/documents/{created['document_id']}")).json()
    assert reopened["source_text"] == CS_TEXT
    assert reopened["title"] == "Paper"


async def test_missing_document_is_a_404(client) -> None:
    assert (await client.get("/api/export/documents/999999")).status_code == 404
