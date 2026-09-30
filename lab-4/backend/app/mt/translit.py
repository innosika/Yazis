"""Practical transcription of English words into Cyrillic.

Names and neologisms are the permanent tail of any bilingual dictionary: no snapshot of
FreeDict will ever contain "Vaswani", "tokenizer" or "Kubernetes". A word-for-word
translator has three options for them - leave them in Latin script, drop them, or
transcribe them. Transcription is the one that produces readable Russian, and it is what a
human translator does with the same input.

This is *practical transcription* (практическая транскрипция), not transliteration: it
follows the conventional English-to-Russian correspondences by sound rather than by letter,
which is why "ch" becomes «ч» and "th" becomes «т», not «цх» and «тх».
"""

import re

# Digraphs and trigraphs first: order in this list is the rule-application order, and a
# two-letter rule must be tried before either of its letters.
_MULTI: list[tuple[str, str]] = [
    ("sch", "ш"),
    ("tch", "ч"),
    ("dge", "дж"),
    ("igh", "ай"),
    ("ough", "оу"),
    ("augh", "оу"),
    ("eigh", "ей"),
    ("tion", "шн"),
    ("sion", "жн"),
    ("cia", "ша"),
    ("cio", "шо"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("th", "т"),
    ("ph", "ф"),
    ("wh", "у"),
    ("ck", "к"),
    ("kn", "н"),
    ("wr", "р"),
    ("qu", "кв"),
    ("gh", "г"),
    ("ng", "нг"),
    ("oo", "у"),
    ("ee", "и"),
    ("ea", "и"),
    ("ie", "и"),
    ("ei", "ей"),
    ("ey", "ей"),
    ("ai", "ей"),
    ("ay", "ей"),
    ("au", "о"),
    ("aw", "о"),
    ("ou", "ау"),
    ("ow", "оу"),
    ("oa", "оу"),
    ("oi", "ой"),
    ("oy", "ой"),
    ("ue", "ю"),
    ("ui", "уи"),
    ("eu", "ю"),
    ("ew", "ю"),
    ("ya", "я"),
    ("yu", "ю"),
    ("yo", "йо"),
    ("ye", "е"),
    ("ll", "лл"),
    ("ss", "сс"),
    ("tt", "тт"),
    ("pp", "пп"),
    ("mm", "мм"),
    ("nn", "нн"),
    ("ff", "фф"),
    ("rr", "рр"),
    ("dd", "дд"),
    ("gg", "гг"),
    ("bb", "бб"),
    ("cc", "кк"),
    ("x", "кс"),
]

_SINGLE: dict[str, str] = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "дж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "y": "и",
    "z": "з",
    "'": "",
    "-": "-",
}

# "c" is /s/ before a front vowel: Cecil -> «Сесил», not «Кекил».
_SOFT_C = re.compile(r"c(?=[eiy])")
# A trailing silent "e" after a consonant is not pronounced: Kate -> «Кейт».
_SILENT_E = re.compile(r"(?<=[bcdfgklmnprstvz])e$")


def transcribe(word: str) -> str:
    """Transcribe one English word into Cyrillic, preserving its capitalisation pattern."""
    if not word:
        return word

    source = word.lower()
    source = _SOFT_C.sub("с", source)
    source = _SILENT_E.sub("", source)

    out: list[str] = []
    position = 0
    while position < len(source):
        for pattern, replacement in _MULTI:
            if source.startswith(pattern, position):
                out.append(replacement)
                position += len(pattern)
                break
        else:
            character = source[position]
            out.append(_SINGLE.get(character, character))
            position += 1

    result = "".join(out)
    # Word-initial /e/ is «э», not «е»: embedding -> «эмбеддинг», Emma -> «Эмма».
    if source.startswith("e") and result.startswith("е"):
        result = "э" + result[1:]
    if word.isupper() and len(word) > 1:
        return result.upper()
    if word[:1].isupper():
        return result[:1].upper() + result[1:]
    return result


def transcribe_phrase(text: str) -> str:
    return " ".join(transcribe(part) for part in text.split())
