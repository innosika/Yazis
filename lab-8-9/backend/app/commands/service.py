"""Voice commands end to end: effective command set, matching pipeline, recognition."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select

from app.asr.filters import is_hallucination, subtract_echo
from app.asr.router import ASRRouter
from app.commands.catalog import BY_ID, CATALOG, LANGUAGES
from app.commands.llm import LLMIntent
from app.commands.matcher import (
    CommandSpec,
    Match,
    Matcher,
    Section,
    prepare,
    resolve_section,
    resolve_voice,
    sections_from_structure,
)
from app.db import models
from app.db.base import session

log = logging.getLogger(__name__)

PROMPTS = {
    "en": "Voice commands for a research paper reader: pause, resume, next sentence, go to "
    "section 3, faster, slower, read the abstract, explain attention, summarize.",
    "ru": "Голосовые команды: пауза, продолжай, дальше, раздел 3, быстрее, медленнее, "
    "читай аннотацию, объясни термин.",
    "de": "Sprachbefehle: Pause, weiter, nächster Satz, Abschnitt 3, schneller, langsamer, "
    "lies die Zusammenfassung.",
    "fr": "Commandes vocales : pause, reprends, suivant, section 3, plus vite, moins vite, "
    "lis le résumé.",
}
DICTATION_PROMPT = {
    "en": "Dictation of notes about a computer science paper.",
    "ru": "Диктовка заметок о научной статье.",
    "de": "Diktat von Notizen zu einem Informatik-Artikel.",
    "fr": "Dictée de notes sur un article d'informatique.",
}


@dataclass
class EffectiveCommand:
    id: str
    title: str
    category: str
    description: str
    enabled: bool
    builtin: bool
    customized: bool
    slots: list[str]
    needs_llm: bool
    phrases: dict[str, list[str]]
    reply: str
    steps: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Outcome:
    utterance: str
    normalized: str
    match: Match | None
    suggestions: list[dict[str, Any]]
    stages: list[str]
    match_ms: float

    def as_dict(self, commands: dict[str, EffectiveCommand]) -> dict[str, Any]:
        match = None
        if self.match is not None:
            m = self.match
            cmd = commands.get(m.command_id)
            match = {
                "command": m.command_id,
                "title": m.title,
                "phrase": m.phrase,
                "method": m.method,
                "confidence": m.confidence,
                "slots": m.slots,
                "alternatives": m.alternatives,
                "reply": cmd.reply if cmd else "",
                "steps": cmd.steps if cmd else [],
                "builtin": cmd.builtin if cmd else True,
            }
        return {
            "utterance": self.utterance,
            "normalized": self.normalized,
            "match": match,
            "suggestions": self.suggestions,
            "stages": self.stages,
            "match_ms": round(self.match_ms, 1),
        }


class CommandService:
    def __init__(self, asr: ASRRouter | None, intent: LLMIntent | None) -> None:
        self.asr = asr
        self.intent = intent
        self._matchers: dict[str, Matcher] = {}
        self._commands: dict[str, EffectiveCommand] = {}
        self.reload()

    # ------------------------------------------------------------- command set

    def reload(self) -> None:
        with session() as s:
            overrides = {o.command_id: o for o in s.scalars(select(models.CommandOverride))}
            customs = list(
                s.scalars(select(models.CustomCommand).order_by(models.CustomCommand.created_at))
            )
            commands: dict[str, EffectiveCommand] = {}
            for c in CATALOG:
                o = overrides.get(c.id)
                phrases = {lang: list(c.phrases.get(lang, ())) for lang in LANGUAGES}
                if o is not None and o.phrases:
                    for lang, items in o.phrases.items():
                        if lang in phrases:
                            phrases[lang] = list(items)
                commands[c.id] = EffectiveCommand(
                    id=c.id,
                    title=c.title,
                    category=c.category,
                    description=c.description,
                    enabled=o.enabled if o is not None else True,
                    builtin=True,
                    customized=o is not None,
                    slots=list(c.slots),
                    needs_llm=c.needs_llm,
                    phrases=phrases,
                    reply=c.reply,
                )
            for cc in customs:
                cid = f"custom:{cc.id}"
                commands[cid] = EffectiveCommand(
                    id=cid,
                    title=cc.name,
                    category="custom",
                    description=cc.reply or cc.name,
                    enabled=cc.enabled,
                    builtin=False,
                    customized=True,
                    slots=[],
                    needs_llm=False,
                    phrases={lang: list(cc.phrases.get(lang, [])) for lang in LANGUAGES},
                    reply=cc.reply,
                    steps=list(cc.steps),
                )
        self._commands = commands
        self._matchers = {}

    def commands(self) -> list[EffectiveCommand]:
        return list(self._commands.values())

    def get(self, cid: str) -> EffectiveCommand | None:
        return self._commands.get(cid)

    def _specs(self, lang: str, llm_available: bool) -> list[CommandSpec]:
        return [
            CommandSpec(
                c.id, c.title, c.phrases.get(lang, []), tuple(c.slots), c.needs_llm, c.description
            )
            for c in self._commands.values()
            if c.enabled and (llm_available or not c.needs_llm)
        ]

    def matcher(self, lang: str) -> Matcher:
        key = f"{lang}:{int(self.intent is not None)}"
        if key not in self._matchers:
            self._matchers[key] = Matcher(self._specs(lang, self.intent is not None), lang)
        return self._matchers[key]

    def prompt(self, lang: str) -> str:
        return PROMPTS.get(lang, PROMPTS["en"])

    # ------------------------------------------------------------- matching

    async def match(
        self,
        utterance: str,
        lang: str,
        sections: list[Section],
        *,
        playing: bool = False,
        allow_llm: bool = True,
    ) -> Outcome:
        started = time.monotonic()
        normalized = prepare(utterance, lang)
        stages = ["normalize"]
        matcher = self.matcher(lang)
        found = matcher.templates(normalized, sections)
        stages.append("template")
        if found:
            return Outcome(utterance, normalized, found[0], [], stages, _ms(started))
        fuzzy = matcher.fuzzy(normalized, strict=playing)
        stages.append("fuzzy")
        strong = [m for m in fuzzy if m.method == "fuzzy"]
        if strong:
            return Outcome(utterance, normalized, strong[0], [], stages, _ms(started))
        suggestions = [
            {
                "command": m.command_id,
                "title": m.title,
                "phrase": m.phrase,
                "confidence": m.confidence,
            }
            for m in fuzzy
        ]
        words = len(normalized.split())
        if allow_llm and not playing and self.intent is not None and 1 <= words <= 12:
            stages.append("llm")
            specs = self._specs(lang, True)
            llm_match = await self.intent.classify(utterance, lang, specs)
            if llm_match is not None:
                resolved = self._resolve_llm_slots(llm_match, sections)
                if resolved is not None:
                    return Outcome(
                        utterance, normalized, resolved, suggestions, stages, _ms(started)
                    )
        return Outcome(utterance, normalized, None, suggestions, stages, _ms(started))

    def _resolve_llm_slots(self, m: Match, sections: list[Section]) -> Match | None:
        cmd = self._commands.get(m.command_id)
        if cmd is None:
            return None
        text = m.slots.pop("text", None)
        if "section" in cmd.slots and m.slots.get("number") is None:
            if not text:
                return None
            sec = resolve_section(text, sections)
            if sec is None:
                return None
            m.slots.update(section=text, section_block=sec.block, section_title=sec.title)
        if "voice" in cmd.slots:
            voice = resolve_voice(text or "")
            if voice is None:
                return None
            m.slots["voice"] = voice
        if "term" in cmd.slots:
            if not text:
                return None
            m.slots["term"] = text
        if cmd.slots == ["number"] and m.slots.get("number") is None:
            return None
        return m

    # ----------------------------------------------------------- recognition

    async def recognize(
        self,
        wav: bytes,
        *,
        lang: str,
        mode: str,
        engine: str,
        playing: bool,
        played_text: str,
        document_id: str | None,
        allow_llm: bool,
    ) -> dict[str, Any]:
        if self.asr is None:
            raise RuntimeError("speech recognition is not configured")
        prompt = DICTATION_PROMPT[lang] if mode == "dictation" else self.prompt(lang)
        t = await self.asr.transcribe(wav, lang, prompt, engine, playing)
        result: dict[str, Any] = {
            "transcript": t.text,
            "engine": t.engine,
            "language": t.language or lang,
            "notes": t.notes,
            "asr_ms": round(t.ms, 1),
            "audio_s": round(t.duration, 2),
            "rejected": None,
            "echo_ratio": 0.0,
            "outcome": None,
        }
        reason = is_hallucination(t, prompt)
        if reason:
            result["rejected"] = reason
            return result
        text = t.text
        if playing and played_text:
            echo = subtract_echo(text, played_text)
            result["echo_ratio"] = round(echo.echo_ratio, 2)
            if not echo.residual.strip():
                result["rejected"] = "echo"
                return result
            text = echo.residual
        if mode == "dictation":
            stop = await self.match(text, lang, [], playing=False, allow_llm=False)
            if (
                stop.match
                and stop.match.command_id in {"stop_listening", "stop", "pause"}
                and stop.match.confidence >= 0.9
            ):
                result["outcome"] = stop.as_dict(self._commands)
            return result
        sections = _sections_for(document_id)
        outcome = await self.match(text, lang, sections, playing=playing, allow_llm=allow_llm)
        result["outcome"] = outcome.as_dict(self._commands)
        return result


def _ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _sections_for(document_id: str | None) -> list[Section]:
    if not document_id:
        return []
    with session() as s:
        row = s.get(models.Document, document_id)
        return sections_from_structure(row.structure if row else None)


def command_dict(c: EffectiveCommand) -> dict[str, Any]:
    return asdict(c)


def builtin_ids() -> set[str]:
    return set(BY_ID)
