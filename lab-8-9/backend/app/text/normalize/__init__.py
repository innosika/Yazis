"""CS-domain text normalization: source text -> spoken text + source/spoken offset map."""

from __future__ import annotations

from app.text.normalize.engine import Context, SpokenText, join, run
from app.text.normalize.rules import rules_for

# Bumped whenever a rule changes what is spoken, so cached audio is never stale.
NORMALIZER_VERSION = "1"

__all__ = ["NORMALIZER_VERSION", "Context", "SpokenText", "normalize"]


def normalize(text: str, ctx: Context | None = None) -> SpokenText:
    ctx = ctx or Context()
    segments = run(text, rules_for(ctx), ctx)
    spoken = join(text, segments)
    if ctx.heading and spoken.text and spoken.text[-1] not in ".!?:":
        spoken = SpokenText(spoken.source, spoken.text + ".", spoken.pieces)
    return spoken
