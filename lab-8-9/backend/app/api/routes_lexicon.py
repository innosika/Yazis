from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import models
from app.db.base import session
from app.state import state
from app.text.normalize.rules import builtin_lexicon

router = APIRouter(prefix="/lexicon", tags=["pronunciation"])


class Entry(BaseModel):
    term: str = Field(..., min_length=1, max_length=100)
    say_as: str = Field(..., min_length=1, max_length=200)


class EntryOut(Entry):
    id: int


class LexiconOut(BaseModel):
    entries: list[EntryOut]
    builtin: int


def refresh() -> None:
    with session() as s:
        rows = s.scalars(select(models.LexiconEntry)).all()
        table = {r.term: r.say_as for r in rows}
    if state.tts is not None:
        state.tts.set_lexicon(table)


@router.get("", response_model=LexiconOut)
def list_entries() -> LexiconOut:
    with session() as s:
        rows = s.scalars(select(models.LexiconEntry).order_by(models.LexiconEntry.term)).all()
        entries = [EntryOut(id=r.id, term=r.term, say_as=r.say_as) for r in rows]
    words, spell = builtin_lexicon()
    return LexiconOut(entries=entries, builtin=len(words) + len(spell))


@router.post("", response_model=EntryOut, status_code=201)
def add_entry(entry: Entry) -> EntryOut:
    term = entry.term.strip()
    with session() as s:
        row = s.scalar(select(models.LexiconEntry).where(models.LexiconEntry.term == term))
        if row is None:
            row = models.LexiconEntry(term=term, say_as=entry.say_as.strip())
            s.add(row)
        else:
            row.say_as = entry.say_as.strip()
        s.flush()
        out = EntryOut(id=row.id, term=row.term, say_as=row.say_as)
    refresh()
    return out


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int) -> None:
    with session() as s:
        row = s.get(models.LexiconEntry, entry_id)
        if row is None:
            raise HTTPException(404)
        s.delete(row)
    refresh()
