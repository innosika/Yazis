"""Last-resort intent recognition: let an LLM map a free-form request onto one command.

Constrained decoding (strict JSON schema, ``command`` is an enum of the enabled
command ids plus "none") means the model cannot invent an action. Results are cached
per (utterance, command set) so a repeated phrase costs one request.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from typing import Any

from app.commands.matcher import CommandSpec, Match
from app.llm.client import GroqLLM, LLMError

log = logging.getLogger(__name__)
LANG_NAMES = {"en": "English", "ru": "Russian", "de": "German", "fr": "French"}


class LLMIntent:
    def __init__(self, llm: GroqLLM, cache_size: int = 256) -> None:
        self.llm = llm
        self._cache: OrderedDict[str, Match | None] = OrderedDict()
        self._size = cache_size

    async def classify(
        self, utterance: str, lang: str, commands: list[CommandSpec]
    ) -> Match | None:
        ids = [c.id for c in commands]
        key = hashlib.sha1(f"{lang}|{utterance}|{','.join(ids)}".encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        lines = []
        for c in commands:
            slot = f" (needs: {', '.join(c.slots)})" if c.slots else ""
            lines.append(f"- {c.id}: {c.description or c.title}{slot}")
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "command": {"type": "string", "enum": [*ids, "none"]},
                "number": {"type": ["number", "null"]},
                "text": {"type": ["string", "null"]},
                "confidence": {"type": "number"},
            },
            "required": ["command", "number", "text", "confidence"],
            "additionalProperties": False,
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You route spoken requests to the voice commands of a reader app for research "
                    "papers. The user speaks "
                    + LANG_NAMES.get(lang, "English")
                    + ". Pick the single "
                    "command the user clearly asks for, or 'none' if the utterance is not a request "
                    "to the app (chit-chat, reading along, noise). Put a number argument in 'number' "
                    "(speed, section number) and a text argument in 'text' (section name, voice name, "
                    "term to explain). Confidence is 0..1.\n\nCommands:\n" + "\n".join(lines)
                ),
            },
            {"role": "user", "content": utterance},
        ]
        try:
            data = await self.llm.json(messages, schema, max_tokens=300, temperature=0.0)
        except LLMError as exc:
            log.info("LLM intent unavailable: %s", exc)
            return None
        cmd_id = data.get("command")
        result: Match | None = None
        if (
            cmd_id
            and cmd_id != "none"
            and cmd_id in ids
            and float(data.get("confidence", 0)) >= 0.6
        ):
            spec = next(c for c in commands if c.id == cmd_id)
            slots: dict[str, Any] = {}
            if data.get("number") is not None:
                slots["number"] = float(data["number"])
            if data.get("text"):
                slots["text"] = str(data["text"])
            result = Match(
                cmd_id, spec.title, utterance, "llm", round(float(data["confidence"]), 3), slots
            )
        self._cache[key] = result
        if len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return result
