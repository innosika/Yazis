"""The reading assistant: explain a term in the paper's context, summarize a section.

Answers are written to be *heard*: short, plain sentences, no markdown, no lists, and
formulas described in words, because the reply is read aloud by the same voice.
"""

from __future__ import annotations

import re

from app.llm.client import GroqLLM

SPOKEN_STYLE = (
    "Your answer will be read aloud by a text-to-speech voice. Write plain spoken English "
    "sentences: no markdown, no bullet points, no headings, no LaTeX, no citations. Describe "
    "formulas in words."
)
MAX_CONTEXT_CHARS = 12_000  # ~3K tokens, well inside the free tier's 8K tokens/minute


def _clip(text: str, limit: int = MAX_CONTEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def _spoken(text: str) -> str:
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text).strip()


async def explain(llm: GroqLLM, term: str, context: str, title: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You help a listener understand a computer science paper. "
            + SPOKEN_STYLE
            + " Answer in two to four sentences.",
        },
        {
            "role": "user",
            "content": f"Paper: {title}\n\nPassage the listener is on:\n{_clip(context, 4000)}"
            f'\n\nExplain what "{term}" means here, as you would to a curious student.',
        },
    ]
    return _spoken(await llm.chat(messages, max_tokens=600, temperature=0.3))


async def summarize(llm: GroqLLM, text: str, title: str, section: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You summarize sections of computer science papers for a "
            "listener. " + SPOKEN_STYLE + " Use at most five sentences and keep the key numbers.",
        },
        {"role": "user", "content": f"Paper: {title}\nSection: {section}\n\n{_clip(text)}"},
    ]
    return _spoken(await llm.chat(messages, max_tokens=900, temperature=0.3))
