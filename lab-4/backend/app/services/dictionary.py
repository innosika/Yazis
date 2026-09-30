"""The dictionary utility: browsing, correction, replenishment and sense locking.

This module is requirement R8 - «утилита автоматического пополнения/корректировки
полученного словаря» - and it is deliberately the only way anything reaches the dictionary
tables at runtime. Automatic proposals come from `app.services.enrich`; nothing is written
until the user accepts one, and every user-made row is flagged `is_user` so the
disambiguator can prefer it and so a re-seed can be told apart from hand work.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import DictEntry, DictSense, DictTranslation, OovTerm, SenseOverride
from app.mt.domains import domain_affinity
from app.mt.glosses import content_words, parse_labels
from app.mt.textnorm import normalise_headword, strip_stress
from app.services.enrich import UPOS_TO_DICT_POS, Enricher, Suggestion

_ENTRY_LOADERS = (selectinload(DictEntry.senses).selectinload(DictSense.translations),)


# --------------------------------------------------------------------------- browsing


async def page_entries(
    session: AsyncSession,
    query: str = "",
    pos: str = "",
    only_user: bool = False,
    page_number: int = 1,
    per_page: int = 25,
) -> tuple[int, list[DictEntry]]:
    """One page of entries. Prefix match first, then substring, so search feels immediate."""
    conditions = []
    if query:
        needle = normalise_headword(query)
        conditions.append(
            or_(DictEntry.headword_norm.like(f"{needle}%"), DictEntry.headword_norm == needle)
        )
    if pos:
        conditions.append(DictEntry.pos == pos)
    if only_user:
        conditions.append(DictEntry.is_user.is_(True))

    total = await session.scalar(select(func.count()).select_from(DictEntry).where(*conditions))
    rows = (
        (
            await session.scalars(
                select(DictEntry)
                .where(*conditions)
                .options(*_ENTRY_LOADERS)
                .order_by(
                    func.length(DictEntry.headword_norm), DictEntry.headword_norm, DictEntry.pos
                )
                .offset((page_number - 1) * per_page)
                .limit(per_page)
            )
        )
        .unique()
        .all()
    )
    return int(total or 0), list(rows)


async def get_entry(session: AsyncSession, entry_id: int) -> DictEntry | None:
    return await session.scalar(
        select(DictEntry).where(DictEntry.id == entry_id).options(*_ENTRY_LOADERS)
    )


async def _reload(session: AsyncSession, entry_id: int) -> DictEntry | None:
    """Re-read an entry after a write, ignoring anything the session still has cached.

    The correction helpers delete rows with a bulk statement, which the ORM's identity map
    never sees. Sessions are created with `expire_on_commit=False`, so without this the
    caller would be handed the collection as it looked *before* the write - a sense whose
    equivalents had just been replaced would come back with the old ones.
    """
    session.expire_all()
    return await get_entry(session, entry_id)


async def dictionary_stats(session: AsyncSession) -> dict:
    entries = await session.scalar(select(func.count()).select_from(DictEntry)) or 0
    senses = await session.scalar(select(func.count()).select_from(DictSense)) or 0
    translations = await session.scalar(select(func.count()).select_from(DictTranslation)) or 0
    user_entries = (
        await session.scalar(
            select(func.count()).select_from(DictEntry).where(DictEntry.is_user.is_(True))
        )
        or 0
    )
    user_translations = (
        await session.scalar(
            select(func.count())
            .select_from(DictTranslation)
            .where(DictTranslation.is_user.is_(True))
        )
        or 0
    )
    multiword = (
        await session.scalar(
            select(func.count()).select_from(DictEntry).where(DictEntry.word_count > 1)
        )
        or 0
    )
    by_pos = {
        (pos or "—"): count
        for pos, count in (
            await session.execute(
                select(DictEntry.pos, func.count())
                .group_by(DictEntry.pos)
                .order_by(func.count().desc())
                .limit(12)
            )
        ).all()
    }
    return {
        "entries": int(entries),
        "senses": int(senses),
        "translations": int(translations),
        "user_entries": int(user_entries),
        "user_translations": int(user_translations),
        "multiword_units": int(multiword),
        "by_pos": by_pos,
    }


# ------------------------------------------------------------------------- correction


async def create_entry(
    session: AsyncSession,
    headword: str,
    pos: str | None,
    senses: list[tuple[str, list[str], list[str]]],
    ipa: str | None = None,
    source: str = "user",
) -> DictEntry:
    """Create a user entry, or merge new senses into an existing one.

    Merging rather than failing on a duplicate is the behaviour the utility needs: accepting
    a suggestion for a word that already has an entry under another part of speech, or
    adding a missing sense to an existing entry, are both ordinary actions.
    """
    norm = normalise_headword(headword)
    existing = await session.scalar(
        select(DictEntry)
        .where(DictEntry.headword_norm == norm, DictEntry.pos == pos)
        .options(*_ENTRY_LOADERS)
    )

    entry = existing or DictEntry(
        headword=headword.strip(),
        headword_norm=norm,
        pos=pos,
        ipa=ipa,
        word_count=len(norm.split()),
        source=source,
        is_user=True,
    )
    if existing is None:
        session.add(entry)
        await session.flush()
        # A just-flushed instance has no loaded `senses` collection, and touching it here
        # would emit a lazy load from inside the async session - which SQLAlchemy cannot do.
        next_index = 0
    else:
        next_index = max((sense.idx for sense in existing.senses), default=-1) + 1
    for gloss, labels, forms in senses:
        parsed_labels, definition = parse_labels(gloss)
        sense = DictSense(
            entry_id=entry.id,
            idx=next_index,
            gloss=gloss,
            labels=labels or parsed_labels,
            domain_scores=domain_affinity(labels or parsed_labels, content_words(definition)),
        )
        session.add(sense)
        await session.flush()
        for order, form in enumerate(_clean_forms(forms)):
            session.add(
                DictTranslation(
                    sense_id=sense.id,
                    idx=order,
                    form_accented=form,
                    form_plain=strip_stress(form),
                    is_user=True,
                )
            )
        next_index += 1

    await session.commit()
    refreshed = await _reload(session, entry.id)
    if refreshed is None:  # pragma: no cover - the row was just committed
        raise RuntimeError("the entry disappeared immediately after being written")
    return refreshed


async def patch_entry(
    session: AsyncSession,
    entry_id: int,
    headword: str | None = None,
    pos: str | None = None,
    ipa: str | None = None,
) -> DictEntry | None:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return None
    if headword:
        entry.headword = headword.strip()
        entry.headword_norm = normalise_headword(headword)
        entry.word_count = len(entry.headword_norm.split())
    if pos is not None:
        entry.pos = pos
    if ipa is not None:
        entry.ipa = ipa or None
    entry.is_user = True
    await session.commit()
    return await _reload(session, entry_id)


async def delete_entry(session: AsyncSession, entry_id: int) -> bool:
    result = await session.execute(delete(DictEntry).where(DictEntry.id == entry_id))
    await session.commit()
    return bool(result.rowcount)


async def add_sense(
    session: AsyncSession, entry_id: int, gloss: str, labels: list[str], forms: list[str]
) -> DictEntry | None:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return None
    parsed_labels, definition = parse_labels(gloss)
    sense = DictSense(
        entry_id=entry.id,
        idx=max((s.idx for s in entry.senses), default=-1) + 1,
        gloss=gloss,
        labels=labels or parsed_labels,
        domain_scores=domain_affinity(labels or parsed_labels, content_words(definition)),
    )
    session.add(sense)
    await session.flush()
    for order, form in enumerate(_clean_forms(forms)):
        session.add(
            DictTranslation(
                sense_id=sense.id,
                idx=order,
                form_accented=form,
                form_plain=strip_stress(form),
                is_user=True,
            )
        )
    entry.is_user = True
    await session.commit()
    return await _reload(session, entry_id)


async def patch_sense(
    session: AsyncSession,
    sense_id: int,
    gloss: str | None = None,
    labels: list[str] | None = None,
) -> DictEntry | None:
    sense = await session.get(DictSense, sense_id)
    if sense is None:
        return None
    if gloss is not None:
        sense.gloss = gloss
    if labels is not None:
        sense.labels = labels
    _, definition = parse_labels(sense.gloss or "")
    sense.domain_scores = domain_affinity(list(sense.labels or ()), content_words(definition))
    await session.commit()
    return await _reload(session, sense.entry_id)


async def delete_sense(session: AsyncSession, sense_id: int) -> int | None:
    sense = await session.get(DictSense, sense_id)
    if sense is None:
        return None
    entry_id = sense.entry_id
    await session.delete(sense)
    await session.commit()
    session.expire_all()
    return entry_id


async def replace_translations(
    session: AsyncSession, sense_id: int, forms: list[str]
) -> DictEntry | None:
    """Replace a sense's equivalents, in the order given.

    Order is meaningful: the first equivalent is the one the translator uses, so reordering
    is itself a correction - and the most common one a user will want to make.
    """
    sense = await session.get(DictSense, sense_id)
    if sense is None:
        return None
    await session.execute(delete(DictTranslation).where(DictTranslation.sense_id == sense_id))
    for order, form in enumerate(_clean_forms(forms)):
        session.add(
            DictTranslation(
                sense_id=sense_id,
                idx=order,
                form_accented=form,
                form_plain=strip_stress(form),
                is_user=True,
            )
        )
    entry = await session.get(DictEntry, sense.entry_id)
    if entry is not None:
        entry.is_user = True
    await session.commit()
    return await _reload(session, sense.entry_id)


def _clean_forms(forms: list[str]) -> list[str]:
    out: list[str] = []
    for form in forms:
        cleaned = " ".join((form or "").split())
        if cleaned and cleaned not in out:
            out.append(cleaned[:200])
    return out


# ----------------------------------------------------------------- replenishment queue


async def record_oov(session: AsyncSession, mentions: list[tuple[str, str, str, int]]) -> None:
    """Add or bump the out-of-vocabulary words a translation run met.

    Words already accepted or dismissed keep their status: the queue is a to-do list, and a
    word the user has already ruled on must not come back.
    """
    if not mentions:
        return
    for lemma, upos, context, occurrences in mentions:
        stmt = (
            insert(OovTerm)
            .values(
                lemma=lemma[:200],
                pos=upos[:16],
                occurrences=occurrences,
                context=context[:500],
                status="pending",
            )
            .on_conflict_do_update(
                constraint="uq_oov_term_lemma_pos",
                set_={
                    "occurrences": OovTerm.occurrences + occurrences,
                    "last_seen": func.now(),
                    "context": func.coalesce(OovTerm.context, context[:500]),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def page_oov(
    session: AsyncSession, status: str = "pending", limit: int = 50
) -> tuple[int, int, list[OovTerm]]:
    conditions = [OovTerm.status == status] if status else []
    total = await session.scalar(select(func.count()).select_from(OovTerm).where(*conditions))
    pending = await session.scalar(
        select(func.count()).select_from(OovTerm).where(OovTerm.status == "pending")
    )
    rows = (
        await session.scalars(
            select(OovTerm)
            .where(*conditions)
            .order_by(OovTerm.occurrences.desc(), OovTerm.last_seen.desc())
            .limit(limit)
        )
    ).all()
    return int(total or 0), int(pending or 0), list(rows)


async def fill_suggestions(
    session: AsyncSession, enricher: Enricher, limit: int = 20
) -> list[OovTerm]:
    """Compute proposals for queued words that do not have one yet."""
    rows = (
        await session.scalars(
            select(OovTerm)
            .where(OovTerm.status == "pending", OovTerm.suggestion.is_(None))
            .order_by(OovTerm.occurrences.desc())
            .limit(limit)
        )
    ).all()
    for row in rows:
        suggestion = await enricher.suggest(row.lemma, row.pos)
        row.suggestion = suggestion.as_dict()
    if rows:
        await session.commit()
    return list(rows)


async def suggest_for(enricher: Enricher, lemma: str, upos: str) -> Suggestion:
    return await enricher.suggest(lemma, upos)


async def accept_oov(
    session: AsyncSession,
    oov_id: int,
    forms: list[str],
    gloss: str = "",
    pos: str | None = None,
) -> DictEntry | None:
    """Turn a queued word into a dictionary entry."""
    term = await session.get(OovTerm, oov_id)
    if term is None:
        return None

    dict_pos = pos or UPOS_TO_DICT_POS.get(term.pos, "n")
    entry = await create_entry(
        session,
        headword=term.lemma,
        pos=dict_pos,
        senses=[(gloss or f"Added from the replenishment queue ({term.pos}).", [], forms)],
    )
    term.status = "accepted"
    await session.commit()
    return entry


async def dismiss_oov(session: AsyncSession, oov_id: int) -> bool:
    term = await session.get(OovTerm, oov_id)
    if term is None:
        return False
    term.status = "dismissed"
    await session.commit()
    return True


# ------------------------------------------------------------------- sense overrides


async def load_overrides(
    session: AsyncSession, domain: str
) -> dict[tuple[str, str], tuple[int, int | None]]:
    """The locks that apply to a domain, in the shape the disambiguator expects."""
    rows = (
        await session.scalars(select(SenseOverride).where(SenseOverride.domain_code == domain))
    ).all()
    return {(row.headword_norm, row.pos): (row.sense_id, row.translation_id) for row in rows}


async def list_overrides(session: AsyncSession) -> list[dict]:
    rows = (
        await session.scalars(select(SenseOverride).order_by(SenseOverride.created_at.desc()))
    ).all()
    out: list[dict] = []
    for row in rows:
        sense = await session.get(DictSense, row.sense_id)
        translation = (
            await session.get(DictTranslation, row.translation_id) if row.translation_id else None
        )
        if translation is None and sense is not None:
            translation = next(iter(sense.translations), None)
        out.append(
            {
                "id": row.id,
                "headword_norm": row.headword_norm,
                "pos": row.pos,
                "domain_code": row.domain_code,
                "sense_id": row.sense_id,
                "translation_id": row.translation_id,
                "translation": translation.form_plain if translation else "",
                "gloss": sense.gloss if sense else "",
                "note": row.note,
                "created_at": _iso(row.created_at),
            }
        )
    return out


async def set_override(
    session: AsyncSession,
    headword: str,
    pos: str,
    domain_code: str,
    sense_id: int,
    translation_id: int | None = None,
    note: str | None = None,
) -> None:
    stmt = (
        insert(SenseOverride)
        .values(
            headword_norm=normalise_headword(headword),
            pos=pos,
            domain_code=domain_code,
            sense_id=sense_id,
            translation_id=translation_id,
            note=note,
        )
        .on_conflict_do_update(
            constraint="uq_sense_override_word_pos_domain",
            set_={"sense_id": sense_id, "translation_id": translation_id, "note": note},
        )
    )
    await session.execute(stmt)
    await session.commit()


async def delete_override(session: AsyncSession, override_id: int) -> bool:
    result = await session.execute(delete(SenseOverride).where(SenseOverride.id == override_id))
    await session.commit()
    return bool(result.rowcount)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""
