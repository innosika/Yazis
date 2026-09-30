"""Process-wide singletons.

spaCy and pymorphy3 each take seconds to load and hundreds of megabytes of RAM. They are
created once during app startup and shared; nothing here is request-scoped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.mt.analysis import Analyzer
    from app.mt.morphgen import MorphGenerator

_analyzer: Analyzer | None = None
_morph: MorphGenerator | None = None
_ready = False


def init() -> None:
    """Load the linguistic resources. Called once from the app's lifespan."""
    global _analyzer, _morph, _ready
    from app.mt.analysis import Analyzer
    from app.mt.morphgen import MorphGenerator

    _analyzer = Analyzer()
    _morph = MorphGenerator()
    _ready = True


def analyzer() -> Analyzer:
    if _analyzer is None:
        raise RuntimeError("linguistic resources are not loaded yet")
    return _analyzer


def morph() -> MorphGenerator:
    if _morph is None:
        raise RuntimeError("linguistic resources are not loaded yet")
    return _morph


def is_ready() -> bool:
    return _ready
