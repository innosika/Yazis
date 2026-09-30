"""Groq chat completions (OpenAI-compatible), with strict JSON-schema output."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class GroqLLM:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self.api_key = api_key
        self.model = model
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self._cooldown_until = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self._cooldown_until

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 400,
        temperature: float = 0.2,
        timeout_s: float = 20.0,
    ) -> str:
        if not self.available:
            raise LLMError("the assistant is cooling down after hitting the rate limit")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if self.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "strict": True, "schema": schema},
            }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(
                    self.url, headers={"Authorization": f"Bearer {self.api_key}"}, json=body
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"assistant unreachable: {exc.__class__.__name__}") from exc
        if r.status_code == 429:
            retry = r.headers.get("retry-after", "30")
            try:
                self._cooldown_until = time.monotonic() + float(retry)
            except ValueError:
                self._cooldown_until = time.monotonic() + 30
            raise LLMError("the assistant hit its rate limit, try again shortly")
        if r.status_code >= 400:
            raise LLMError(f"assistant error {r.status_code}: {r.text[:200]}")
        content = r.json()["choices"][0]["message"].get("content") or ""
        return str(content).strip()

    async def json(self, messages: list[dict[str, str]], schema: dict[str, Any], **kw: Any) -> Any:
        text = await self.chat(messages, schema=schema, **kw)
        try:
            return json.loads(text)
        except ValueError as exc:
            raise LLMError("assistant returned invalid JSON") from exc
