"""Spoken numbers to digits in English, Russian, German and French.

Commands only need small numbers: section numbers, speeds like "one point five",
volumes in percent. Recognisers usually write digits already; this covers the cases
where they spell them out ("go to section three", "скорость полтора").
"""

from __future__ import annotations

import re

_EN_UNITS = {
    "zero": 0,
    "oh": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_EN_ORD = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "last": -1,
}

_RU_UNITS = {
    "ноль": 0,
    "нуль": 0,
    "один": 1,
    "одна": 1,
    "одну": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "сто": 100,
}
# Russian ordinals inflect; match on the stem.
_RU_ORD_STEMS = (
    ("перв", 1),
    ("втор", 2),
    ("трет", 3),
    ("четв", 4),
    ("пят", 5),
    ("шест", 6),
    ("седьм", 7),
    ("восьм", 8),
    ("девят", 9),
    ("десят", 10),
    ("последн", -1),
)

_DE_UNITS = {
    "null": 0,
    "eins": 1,
    "ein": 1,
    "eine": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "elf": 11,
    "zwölf": 12,
    "zwanzig": 20,
    "dreißig": 30,
    "vierzig": 40,
    "fünfzig": 50,
    "hundert": 100,
}
_DE_ORD_STEMS = (
    ("erst", 1),
    ("zweit", 2),
    ("dritt", 3),
    ("viert", 4),
    ("fünft", 5),
    ("sechst", 6),
    ("siebt", 7),
    ("acht", 8),
    ("neunt", 9),
    ("zehnt", 10),
    ("letzt", -1),
)

_FR_UNITS = {
    "zéro": 0,
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "vingt": 20,
    "trente": 30,
    "quarante": 40,
    "cinquante": 50,
    "cent": 100,
}
_FR_ORD = {
    "premier": 1,
    "première": 1,
    "deuxième": 2,
    "second": 2,
    "seconde": 2,
    "troisième": 3,
    "quatrième": 4,
    "cinquième": 5,
    "sixième": 6,
    "septième": 7,
    "huitième": 8,
    "neuvième": 9,
    "dixième": 10,
    "dernier": -1,
    "dernière": -1,
}

_POINT = {
    "en": ("point", "dot"),
    "ru": ("точка", "запятая"),
    "de": ("komma", "punkt"),
    "fr": ("virgule", "point"),
}
_HALF = {
    "en": ("and a half",),
    "ru": ("с половиной",),
    "de": ("einhalb",),
    "fr": ("et demi", "et demie"),
}
_ONE_AND_HALF = {
    "ru": ("полтора", "полторы"),
    "de": ("anderthalb", "eineinhalb"),
    "en": (),
    "fr": (),
}


def _cardinal(tokens: list[str], i: int, lang: str) -> tuple[int, int] | None:
    """Parse a cardinal starting at tokens[i]; return (value, tokens consumed)."""
    tok = tokens[i]
    if tok.isdigit():
        return int(tok), 1
    if lang == "en":
        if tok in _EN_UNITS:
            return _EN_UNITS[tok], 1
        if tok in _EN_TENS:
            if (
                i + 1 < len(tokens)
                and tokens[i + 1] in _EN_UNITS
                and 0 < _EN_UNITS[tokens[i + 1]] < 10
            ):
                return _EN_TENS[tok] + _EN_UNITS[tokens[i + 1]], 2
            return _EN_TENS[tok], 1
        if tok == "hundred":
            return 100, 1
        return None
    table = {"ru": _RU_UNITS, "de": _DE_UNITS, "fr": _FR_UNITS}[lang]
    if tok in table:
        value = table[tok]
        # "двадцать один", "vingt et un", "vingt deux"
        j = i + 1
        if value >= 20 and j < len(tokens) and tokens[j] == "et":
            j += 1
        if value >= 20 and j < len(tokens) and tokens[j] in table and 0 < table[tokens[j]] < 10:
            return value + table[tokens[j]], j - i + 1
        return value, 1
    if lang == "de":
        # "einundzwanzig"
        m = re.fullmatch(r"(\w+?)und(\w+)", tok)
        if m and m.group(1) in _DE_UNITS and m.group(2) in _DE_UNITS:
            return _DE_UNITS[m.group(1)] + _DE_UNITS[m.group(2)], 1
    return None


def ordinal(token: str, lang: str) -> int | None:
    if lang == "en":
        if token in _EN_ORD:
            return _EN_ORD[token]
        m = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", token)
        return int(m.group(1)) if m else None
    if lang == "fr":
        return _FR_ORD.get(token)
    stems = _RU_ORD_STEMS if lang == "ru" else _DE_ORD_STEMS if lang == "de" else ()
    for stem, value in stems:
        if token.startswith(stem) and len(token) <= len(stem) + 4:
            # "пять"/"пятый": the cardinal is handled elsewhere; only suffixed forms here.
            if lang == "ru" and token in _RU_UNITS:
                return None
            if lang == "de" and token in _DE_UNITS:
                return None
            return value
    return None


def words_to_digits(text: str, lang: str) -> str:
    """Rewrite spelled-out numbers as digits: 'section three' -> 'section 3',
    'one point five' -> '1.5', 'полтора' -> '1.5'."""
    for phrase in _ONE_AND_HALF.get(lang, ()):
        text = re.sub(rf"\b{phrase}\b", "1.5", text)
    tokens = text.split()
    out: list[str] = []
    i = 0
    points = _POINT.get(lang, ())
    while i < len(tokens):
        parsed = _cardinal(tokens, i, lang)
        if parsed is None:
            out.append(tokens[i])
            i += 1
            continue
        value, used = parsed
        i += used
        number = str(value)
        # decimal part: "one point five", "один и пять", "eins komma fünf"
        if i + 1 < len(tokens) and tokens[i] in points:
            frac = _cardinal(tokens, i + 1, lang)
            if frac is not None and frac[0] < 100:
                number = f"{value}.{frac[0]}"
                i += 1 + frac[1]
        rest = " ".join(tokens[i : i + 3])
        for half in _HALF.get(lang, ()):
            if rest.startswith(half):
                number = f"{value}.5"
                i += len(half.split())
                break
        out.append(number)
    return " ".join(out)


def parse_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))
