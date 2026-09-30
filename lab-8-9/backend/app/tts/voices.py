"""Kokoro-82M English voices with the grades published in the model's VOICES.md.

`featured` voices (grade C and better) are what the voice picker shows by default;
the rest stay one toggle away. The first letter of the id is Kokoro's language code:
`a` American English, `b` British English.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Accent = Literal["us", "gb"]
Gender = Literal["female", "male"]


@dataclass(frozen=True, slots=True)
class Voice:
    id: str
    name: str
    accent: Accent
    gender: Gender
    grade: str
    featured: bool

    @property
    def lang_code(self) -> str:
        return self.id[0]


def _v(vid: str, grade: str, featured: bool) -> Voice:
    accent: Accent = "us" if vid[0] == "a" else "gb"
    gender: Gender = "female" if vid[1] == "f" else "male"
    return Voice(vid, vid.split("_", 1)[1].capitalize(), accent, gender, grade, featured)


ALL_VOICES: tuple[Voice, ...] = (
    _v("af_heart", "A", True),
    _v("af_bella", "A-", True),
    _v("af_nicole", "B-", True),
    _v("af_aoede", "C+", True),
    _v("af_kore", "C+", True),
    _v("af_sarah", "C+", True),
    _v("am_michael", "C+", True),
    _v("am_fenrir", "C+", True),
    _v("am_puck", "C+", True),
    _v("bf_emma", "B-", True),
    _v("bf_isabella", "C", True),
    _v("bm_george", "C", True),
    _v("bm_fable", "C", True),
    _v("af_alloy", "C", False),
    _v("af_nova", "C", False),
    _v("af_sky", "C-", False),
    _v("af_jessica", "D", False),
    _v("af_river", "D", False),
    _v("am_echo", "D", False),
    _v("am_eric", "D", False),
    _v("am_liam", "D", False),
    _v("am_onyx", "D", False),
    _v("am_santa", "D-", False),
    _v("am_adam", "F+", False),
    _v("bf_alice", "D", False),
    _v("bf_lily", "D", False),
    _v("bm_daniel", "D", False),
    _v("bm_lewis", "D+", False),
)

VOICES_BY_ID: dict[str, Voice] = {v.id: v for v in ALL_VOICES}
DEFAULT_VOICE = "af_heart"


def get_voice(voice_id: str) -> Voice:
    try:
        return VOICES_BY_ID[voice_id]
    except KeyError:
        raise ValueError(f"unknown voice {voice_id!r}") from None
