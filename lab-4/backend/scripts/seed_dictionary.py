"""Load the committed dictionary seed into PostgreSQL.

    python -m scripts.seed_dictionary            # no-op if the dictionary is populated
    python -m scripts.seed_dictionary --force    # wipe and reload

Runs as part of `make up`, between `alembic upgrade head` and uvicorn, so the API never
starts against an empty dictionary.

Loading goes through asyncpg's binary COPY rather than the ORM: 62 181 entries, 78 720
senses and 155 000 translations inserted row by row would take minutes, and `make up` has
to feel instant on a fresh machine. Primary keys are therefore assigned here and the
sequences are fast-forwarded afterwards.
"""

import argparse
import asyncio
import gzip
import json
import sys
import time
from pathlib import Path

import asyncpg

from app.config import settings
from app.mt.domains import domain_affinity
from app.mt.glosses import content_words, parse_labels
from app.mt.textnorm import clean_translation, normalise_headword, strip_stress


def dsn_for_asyncpg(sqlalchemy_dsn: str) -> str:
    return sqlalchemy_dsn.replace("postgresql+asyncpg://", "postgresql://")


def read_seed(path: Path) -> tuple[list[tuple], list[tuple], list[tuple], dict[str, int]]:
    """Turn the JSONL seed into COPY-ready row tuples.

    The source lists the same headword more than once when Wiktionary split it across
    etymologies. Those are merged here on (headword, part of speech), because a translator
    asking the dictionary for "bank/noun" wants every sense, not whichever duplicate the
    loader happened to insert last.
    """
    merged: dict[tuple[str, str | None], dict] = {}
    order: list[tuple[str, str | None]] = []

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            headword = (record.get("hw") or "").strip()
            norm = normalise_headword(headword)
            if not norm:
                continue
            key = (norm, record.get("pos"))
            bucket = merged.get(key)
            if bucket is None:
                bucket = {
                    "headword": headword,
                    "norm": norm,
                    "pos": record.get("pos"),
                    "ipa": (record.get("ipa") or [None])[0],
                    "senses": [],
                    "seen": set(),
                }
                merged[key] = bucket
                order.append(key)
            for sense in record.get("senses", []):
                fingerprint = (sense.get("gloss") or "", tuple(t["p"] for t in sense.get("tr", [])))
                if fingerprint in bucket["seen"]:
                    continue
                bucket["seen"].add(fingerprint)
                bucket["senses"].append(sense)

    entries: list[tuple] = []
    senses: list[tuple] = []
    translations: list[tuple] = []
    entry_id = sense_id = translation_id = 0

    for key in order:
        bucket = merged[key]
        if not bucket["senses"]:
            continue
        entry_id += 1
        word_count = len(bucket["norm"].split())
        entries.append(
            (
                entry_id,
                bucket["headword"][:200],
                bucket["norm"][:200],
                bucket["pos"],
                bucket["ipa"][:200] if bucket["ipa"] else None,
                word_count,
                "freedict",
                False,
            )
        )
        for sense_index, sense in enumerate(bucket["senses"]):
            gloss = sense.get("gloss") or ""
            labels, definition = parse_labels(gloss)
            affinity = domain_affinity(labels, content_words(definition))
            sense_id += 1
            senses.append((sense_id, entry_id, sense_index, gloss, labels, json.dumps(affinity)))
            for translation_index, form in enumerate(sense.get("tr", [])):
                accented = clean_translation(form.get("a") or "")
                plain = clean_translation(form.get("p") or strip_stress(accented))
                if not plain:
                    continue
                translation_id += 1
                translations.append(
                    (
                        translation_id,
                        sense_id,
                        translation_index,
                        accented[:200],
                        plain[:200],
                        False,
                    )
                )

    counters = {"entry": entry_id, "sense": sense_id, "translation": translation_id}
    return entries, senses, translations, counters


async def seed(force: bool) -> int:
    path = settings.dictionary_seed
    if not path.exists():
        print(f"dictionary seed not found: {path}", file=sys.stderr)
        print("run `make dict-rebuild` to regenerate it from FreeDict", file=sys.stderr)
        return 1

    connection = await asyncpg.connect(dsn_for_asyncpg(settings.postgres_dsn))
    try:
        existing = await connection.fetchval("SELECT count(*) FROM dict_entry")
        if existing and not force:
            print(f"dictionary already seeded ({existing} entries) - skipping")
            return 0
        if existing:
            # CASCADE also clears sense_override, whose rows point at sense ids that are
            # about to be reassigned. A re-seed is an explicit --force action, so that is
            # the intended behaviour rather than silent data loss.
            print(f"--force: dropping {existing} existing entries")
            await connection.execute("TRUNCATE dict_entry CASCADE")

        started = time.monotonic()
        entries, senses, translations, counters = read_seed(path)
        parsed = time.monotonic()

        async with connection.transaction():
            await connection.copy_records_to_table(
                "dict_entry",
                records=entries,
                columns=[
                    "id",
                    "headword",
                    "headword_norm",
                    "pos",
                    "ipa",
                    "word_count",
                    "source",
                    "is_user",
                ],
            )
            await connection.copy_records_to_table(
                "dict_sense",
                records=senses,
                columns=["id", "entry_id", "idx", "gloss", "labels", "domain_scores"],
            )
            await connection.copy_records_to_table(
                "dict_translation",
                records=translations,
                columns=["id", "sense_id", "idx", "form_accented", "form_plain", "is_user"],
            )
            for table, last in (
                ("dict_entry", counters["entry"]),
                ("dict_sense", counters["sense"]),
                ("dict_translation", counters["translation"]),
            ):
                await connection.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), $1)", last
                )
            await connection.execute("ANALYZE dict_entry, dict_sense, dict_translation")

        print(
            f"seeded {counters['entry']} entries, {counters['sense']} senses, "
            f"{counters['translation']} translations "
            f"(parse {parsed - started:.1f}s, load {time.monotonic() - parsed:.1f}s)"
        )
        return 0
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="wipe the dictionary and reload")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(seed(args.force)))


if __name__ == "__main__":
    main()
