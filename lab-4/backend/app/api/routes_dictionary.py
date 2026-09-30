"""The dictionary utility's endpoints: browse, correct, replenish, lock a sense."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import state
from app.db.base import get_session
from app.db.models import DictEntry, OovTerm
from app.mt.domains import DOMAINS
from app.schemas.dictionary import (
    EntryIn,
    EntryOut,
    EntryPage,
    EntryPatch,
    OovAccept,
    OovPage,
    OverrideIn,
    OverrideOut,
    ScanRequest,
    ScanResult,
    SenseIn,
    SensePatch,
    SuggestionOut,
    TranslationsPatch,
)
from app.services import dictionary
from app.services.enrich import Enricher

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


def _enricher() -> Enricher:
    return Enricher(state.morph())


def _entry_out(entry: DictEntry) -> dict:
    return {
        "id": entry.id,
        "headword": entry.headword,
        "headword_norm": entry.headword_norm,
        "pos": entry.pos,
        "ipa": entry.ipa,
        "word_count": entry.word_count,
        "source": entry.source,
        "is_user": entry.is_user,
        "senses": [
            {
                "id": sense.id,
                "idx": sense.idx,
                "gloss": sense.gloss,
                "labels": list(sense.labels or ()),
                "domain_scores": dict(sense.domain_scores or {}),
                "translations": [
                    {
                        "id": translation.id,
                        "idx": translation.idx,
                        "form_accented": translation.form_accented,
                        "form_plain": translation.form_plain,
                        "is_user": translation.is_user,
                    }
                    for translation in sense.translations
                ],
            }
            for sense in entry.senses
        ],
    }


def _oov_out(term: OovTerm) -> dict:
    return {
        "id": term.id,
        "lemma": term.lemma,
        "pos": term.pos,
        "occurrences": term.occurrences,
        "status": term.status,
        "suggestion": term.suggestion,
        "context": term.context,
        "first_seen": term.first_seen.isoformat() if term.first_seen else "",
        "last_seen": term.last_seen.isoformat() if term.last_seen else "",
    }


# ---------------------------------------------------------------------------- browsing


@router.get("/entries", response_model=EntryPage, summary="Search the dictionary")
async def entries(
    q: str = "",
    pos: str = "",
    only_user: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    total, rows = await dictionary.page_entries(session, q, pos, only_user, page, per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [_entry_out(row) for row in rows],
    }


@router.get("/entries/{entry_id}", response_model=EntryOut, summary="One entry")
async def entry(entry_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    row = await dictionary.get_entry(session, entry_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    return _entry_out(row)


@router.get("/stats", summary="Dictionary size and composition")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    return await dictionary.dictionary_stats(session)


# -------------------------------------------------------------------------- correction


@router.post(
    "/entries",
    response_model=EntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an entry, or merge senses into an existing one",
)
async def create_entry(payload: EntryIn, session: AsyncSession = Depends(get_session)) -> dict:
    row = await dictionary.create_entry(
        session,
        headword=payload.headword,
        pos=payload.pos,
        ipa=payload.ipa,
        senses=[(sense.gloss, sense.labels, sense.translations) for sense in payload.senses],
    )
    return _entry_out(row)


@router.patch("/entries/{entry_id}", response_model=EntryOut, summary="Correct an entry")
async def patch_entry(
    entry_id: int, payload: EntryPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await dictionary.patch_entry(
        session, entry_id, payload.headword, payload.pos, payload.ipa
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    return _entry_out(row)


@router.delete(
    "/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an entry"
)
async def delete_entry(entry_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await dictionary.delete_entry(session, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")


@router.post("/entries/{entry_id}/senses", response_model=EntryOut, summary="Add a sense")
async def add_sense(
    entry_id: int, payload: SenseIn, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await dictionary.add_sense(
        session, entry_id, payload.gloss, payload.labels, payload.translations
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    return _entry_out(row)


@router.patch("/senses/{sense_id}", response_model=EntryOut, summary="Correct a sense")
async def patch_sense(
    sense_id: int, payload: SensePatch, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await dictionary.patch_sense(session, sense_id, payload.gloss, payload.labels)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sense not found")
    return _entry_out(row)


@router.delete("/senses/{sense_id}", response_model=EntryOut, summary="Delete a sense")
async def delete_sense(sense_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    entry_id = await dictionary.delete_sense(session, sense_id)
    if entry_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sense not found")
    row = await dictionary.get_entry(session, entry_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    return _entry_out(row)


@router.put(
    "/senses/{sense_id}/translations",
    response_model=EntryOut,
    summary="Replace a sense's Russian equivalents, in order",
)
async def replace_translations(
    sense_id: int, payload: TranslationsPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await dictionary.replace_translations(session, sense_id, payload.forms)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sense not found")
    return _entry_out(row)


# ---------------------------------------------------------------- replenishment queue


@router.get("/oov", response_model=OovPage, summary="Words the dictionary could not translate")
async def oov(
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    total, pending, rows = await dictionary.page_oov(session, status_filter, limit)
    return {"total": total, "pending": pending, "items": [_oov_out(row) for row in rows]}


@router.post("/oov/suggest", response_model=OovPage, summary="Fill in missing proposals")
async def suggest_queue(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    enricher = _enricher()
    try:
        await dictionary.fill_suggestions(session, enricher, limit)
    finally:
        await enricher.close()
    total, pending, rows = await dictionary.page_oov(session, "pending", 50)
    return {"total": total, "pending": pending, "items": [_oov_out(row) for row in rows]}


@router.get("/suggest", response_model=SuggestionOut, summary="Propose a translation for one word")
async def suggest_one(lemma: str, upos: str = "NOUN") -> dict:
    enricher = _enricher()
    try:
        suggestion = await enricher.suggest(lemma, upos)
    finally:
        await enricher.close()
    return suggestion.as_dict()


@router.post(
    "/scan",
    response_model=ScanResult,
    summary="Scan a text for unknown words and propose translations for all of them",
)
async def scan(payload: ScanRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """The batch form of the replenishment utility.

    Analyses the text, collects every content word the dictionary cannot translate, and
    proposes a translation for each - so a user preparing to translate a paper can close the
    dictionary's gaps in one pass instead of one word at a time.
    """
    from app.mt.lexicon import build_index
    from app.mt.pipeline import Pipeline

    analyzer = state.analyzer()
    analysis = analyzer.analyse(payload.text)
    index = await build_index(session, analysis)
    result = Pipeline(analyzer, state.morph()).run(
        text=payload.text,
        index=index,
        domain=DOMAINS.get(payload.domain, DOMAINS["general"]),
        mode="transfer",
        include_direct=False,
    )

    mentions = result.oov[: payload.limit]
    enricher = _enricher()
    try:
        suggestions = await enricher.suggest_many([(m.lemma, m.upos) for m in mentions])
    finally:
        await enricher.close()

    await dictionary.record_oov(
        session, [(m.lemma, m.upos, m.context, m.occurrences) for m in result.oov]
    )
    return {
        "scanned_words": result.stats.words,
        "found": len(result.oov),
        "suggestions": [suggestion.as_dict() for suggestion in suggestions],
    }


@router.post("/oov/{oov_id}/accept", response_model=EntryOut, summary="Accept a proposal")
async def accept(
    oov_id: int, payload: OovAccept, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await dictionary.accept_oov(session, oov_id, payload.forms, payload.gloss, payload.pos)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "queued word not found")
    return _entry_out(row)


@router.post(
    "/oov/{oov_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT, summary="Reject a proposal"
)
async def dismiss(oov_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await dictionary.dismiss_oov(session, oov_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "queued word not found")


# -------------------------------------------------------------------- sense overrides


@router.get("/overrides", response_model=list[OverrideOut], summary="Locked senses")
async def overrides(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return await dictionary.list_overrides(session)


@router.post(
    "/overrides", status_code=status.HTTP_204_NO_CONTENT, summary="Lock a sense for a subject area"
)
async def set_override(payload: OverrideIn, session: AsyncSession = Depends(get_session)) -> None:
    if payload.domain_code not in DOMAINS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown subject area")
    await dictionary.set_override(
        session,
        headword=payload.headword,
        pos=payload.pos,
        domain_code=payload.domain_code,
        sense_id=payload.sense_id,
        translation_id=payload.translation_id,
        note=payload.note,
    )


@router.delete(
    "/overrides/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a locked sense",
)
async def delete_override(override_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await dictionary.delete_override(session, override_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "override not found")
