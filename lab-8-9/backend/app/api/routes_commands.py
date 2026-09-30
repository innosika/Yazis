from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.commands.catalog import BY_ID, LANGUAGES, MACRO_ACTIONS
from app.commands.matcher import sections_from_structure
from app.commands.service import command_dict
from app.db import models
from app.db.base import session
from app.state import state

router = APIRouter(prefix="/commands", tags=["voice commands"])

Lang = Literal["en", "ru", "de", "fr"]


class OverrideIn(BaseModel):
    enabled: bool | None = None
    phrases: dict[Lang, list[str]] | None = None


class Step(BaseModel):
    action: str
    value: float | str | None = None


class CustomIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phrases: dict[Lang, list[str]]
    steps: list[Step] = Field(..., min_length=1, max_length=10)
    reply: str = Field("", max_length=300)
    enabled: bool = True


class TestIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    language: Lang = "en"
    document_id: str | None = None
    playing: bool = False
    llm_fallback: bool = True


def _clean_phrases(phrases: dict[str, list[str]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lang, items in phrases.items():
        seen: list[str] = []
        for p in items:
            p = re.sub(r"\s+", " ", p).strip()
            if p and p.lower() not in (x.lower() for x in seen):
                seen.append(p[:120])
        out[lang] = seen[:30]
    return out


@router.get("")
def list_commands() -> dict[str, Any]:
    return {
        "commands": [command_dict(c) for c in state.commands.commands()],
        "languages": list(LANGUAGES),
        "macro_actions": [{"action": a, "param": p} for a, p in MACRO_ACTIONS.items()],
    }


@router.post("/test")
async def test_phrase(body: TestIn) -> dict[str, Any]:
    sections = []
    if body.document_id:
        with session() as s:
            row = s.get(models.Document, body.document_id)
            sections = sections_from_structure(row.structure if row else None)
    outcome = await state.commands.match(
        body.text, body.language, sections, playing=body.playing, allow_llm=body.llm_fallback
    )
    return outcome.as_dict({c.id: c for c in state.commands.commands()})  # type: ignore[no-any-return]


@router.put("/{command_id}")
def update_builtin(command_id: str, body: OverrideIn) -> dict[str, Any]:
    if command_id not in BY_ID:
        raise HTTPException(404, "Unknown command")
    with session() as s:
        row = s.get(models.CommandOverride, command_id)
        if row is None:
            row = models.CommandOverride(command_id=command_id, enabled=True, phrases=None)
            s.add(row)
        if body.enabled is not None:
            row.enabled = body.enabled
        if body.phrases is not None:
            merged = dict(row.phrases or {})
            merged.update(_clean_phrases({str(k): v for k, v in body.phrases.items()}))
            row.phrases = merged
    state.commands.reload()
    return command_dict(state.commands.get(command_id))


@router.delete("/{command_id}/override", status_code=204)
def reset_builtin(command_id: str) -> None:
    with session() as s:
        row = s.get(models.CommandOverride, command_id)
        if row is not None:
            s.delete(row)
    state.commands.reload()


def _validate_steps(steps: list[Step]) -> list[dict[str, Any]]:
    out = []
    for st in steps:
        if st.action not in MACRO_ACTIONS:
            raise HTTPException(422, f"Unknown action {st.action!r}")
        out.append({"action": st.action, "value": st.value})
    return out


@router.post("/custom", status_code=201)
def create_custom(body: CustomIn) -> dict[str, Any]:
    phrases = _clean_phrases({str(k): v for k, v in body.phrases.items()})
    if not any(phrases.values()):
        raise HTTPException(422, "Add at least one phrase")
    cid = uuid.uuid4().hex[:10]
    with session() as s:
        s.add(
            models.CustomCommand(
                id=cid,
                name=body.name.strip(),
                enabled=body.enabled,
                phrases=phrases,
                steps=_validate_steps(body.steps),
                reply=body.reply.strip(),
            )
        )
    state.commands.reload()
    return command_dict(state.commands.get(f"custom:{cid}"))


@router.put("/custom/{cid}")
def update_custom(cid: str, body: CustomIn) -> dict[str, Any]:
    with session() as s:
        row = s.get(models.CustomCommand, cid)
        if row is None:
            raise HTTPException(404, "Unknown command")
        row.name = body.name.strip()
        row.enabled = body.enabled
        row.phrases = _clean_phrases({str(k): v for k, v in body.phrases.items()})
        row.steps = _validate_steps(body.steps)
        row.reply = body.reply.strip()
    state.commands.reload()
    return command_dict(state.commands.get(f"custom:{cid}"))


@router.delete("/custom/{cid}", status_code=204)
def delete_custom(cid: str) -> None:
    with session() as s:
        row = s.get(models.CustomCommand, cid)
        if row is None:
            raise HTTPException(404, "Unknown command")
        s.delete(row)
    state.commands.reload()
