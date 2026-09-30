"""Utterance clean-up before matching: case, punctuation, fillers, spelled numbers."""

from __future__ import annotations

import re

from app.commands.numbers import ordinal, words_to_digits

# Politeness and wake-up words that carry no command meaning.
FILLERS: dict[str, tuple[str, ...]] = {
    "en": (
        "hey lector",
        "hi lector",
        "ok lector",
        "okay lector",
        "lector",
        "lecture",
        "please",
        "could you",
        "can you",
        "would you",
        "will you",
        "i want you to",
        "i'd like you to",
        "okay",
        "ok",
        "um",
        "uh",
        "hmm",
        "now",
        "for me",
        "right now",
        "just",
        "alright",
        "all right",
        "so",
        "well",
    ),
    "ru": (
        "эй лектор",
        "лектор",
        "пожалуйста",
        "можешь",
        "можно",
        "давай",
        "окей",
        "ну",
        "так",
        "сейчас",
        "мне",
    ),
    "de": (
        "hey lector",
        "lector",
        "bitte",
        "kannst du",
        "könntest du",
        "okay",
        "ok",
        "jetzt",
        "mal",
        "also",
    ),
    "fr": (
        "hé lector",
        "lector",
        "s'il te plaît",
        "s'il vous plaît",
        "peux-tu",
        "pourrais-tu",
        "d'accord",
        "ok",
        "maintenant",
        "alors",
    ),
}
_ORDINAL_SECTION = {
    "en": re.compile(r"\b(?:the\s+)?(\w+)\s+section\b"),
    "ru": re.compile(r"\b(\w+)\s+раздел\w*\b"),
    "de": re.compile(r"\b(?:den\s+|der\s+)?(\w+)\s+abschnitt\b"),
    "fr": re.compile(r"\b(?:la\s+)?(\w+)\s+section\b"),
}
_SECTION_WORD = {"en": "section", "ru": "раздел", "de": "abschnitt", "fr": "section"}


def normalize(text: str, lang: str) -> str:
    s = text.lower().replace("ё", "е")
    s = re.sub(r"[“”\"«»„]", " ", s)
    s = re.sub(r"(?<=\d)[.,](?=\d)", "‧", s)  # protect decimals
    s = re.sub(r"[^\w\s'‧-]", " ", s)
    s = s.replace("‧", ".")
    s = re.sub(r"\s+-\s+|\s+-|-\s+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for filler in sorted(FILLERS.get(lang, ()), key=len, reverse=True):
        s = re.sub(rf"(?:^|\s){re.escape(filler)}(?=\s|$)", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # "the third section" -> "section 3"
    pattern = _ORDINAL_SECTION.get(lang)
    if pattern is not None:

        def _ord(m: re.Match[str]) -> str:
            value = ordinal(m.group(1), lang)
            return f"{_SECTION_WORD[lang]} {value}" if value is not None else m.group(0)

        s = pattern.sub(_ord, s)
    return words_to_digits(s, lang)
