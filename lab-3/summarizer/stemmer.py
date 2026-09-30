# -*- coding: utf-8 -*-
"""Стемминг — приведение словоформы к основе (stem).

Модуль содержит собственные реализации двух алгоритмов проекта Snowball
(M. Porter), выполненные без внешних зависимостей:

* :class:`RussianStemmer`  — алгоритм «Russian stemming algorithm» (Snowball);
* :class:`EnglishStemmer`  — алгоритм «English (Porter2) stemming algorithm».

Стемминг необходим для того, чтобы разные словоформы одного слова
(«заболевание», «заболевания», «заболеваний») считались одним термином,
иначе частота термина tf занижается в несколько раз.
"""
from __future__ import annotations

import functools

# --------------------------------------------------------------------------
#                        РУССКИЙ СТЕММЕР (Snowball)
# --------------------------------------------------------------------------

_RU_VOWELS = "аеиоуыэюяё"

# Окончания перечислены группами; внутри группы порядок «сначала длинные»
_PERFECTIVE_GERUND_1 = ("вшись", "вши", "в")            # только после а/я
_PERFECTIVE_GERUND_2 = ("ывшись", "ившись", "ывши", "ивши", "ыв", "ив")
_ADJECTIVE = ("иями", "ями", "ими", "ыми", "его", "ого", "ему", "ому", "ее", "ие",
              "ые", "ое", "ей", "ий", "ый", "ой", "ем", "им", "ым", "ом", "их",
              "ых", "ую", "юю", "ая", "яя", "ою", "ею")
_PARTICIPLE_1 = ("ющ", "вш", "нн", "ем", "щ")            # только после а/я
_PARTICIPLE_2 = ("ующ", "ывш", "ивш")
_REFLEXIVE = ("ся", "сь")
_VERB_1 = ("ейте", "уйте", "ете", "йте", "ешь", "нно", "ла", "на", "ли", "ем",
           "ло", "но", "ет", "ют", "ны", "ть", "й", "л", "н")   # после а/я
_VERB_2 = ("ейте", "уйте", "ила", "ыла", "ена", "ите", "или", "ыли", "ило",
           "ыло", "ено", "ует", "уют", "ены", "ить", "ыть", "ишь", "ей", "уй",
           "ил", "ыл", "им", "ым", "ен", "ят", "ит", "ыт", "ую", "ю")
_NOUN = ("иями", "ями", "ами", "иях", "ях", "ах", "ией", "иям", "ием", "ев",
         "ов", "ие", "ье", "еи", "ии", "ей", "ой", "ий", "ям", "ем", "ам",
         "ом", "ия", "ья", "ию", "ью", "а", "е", "и", "й", "о", "у", "ы",
         "ь", "ю", "я")
_SUPERLATIVE = ("ейше", "ейш")
_DERIVATIONAL = ("ость", "ост")


def _rv_index(word: str) -> int:
    """RV — область после первой гласной (индекс её первого символа)."""
    for i, ch in enumerate(word):
        if ch in _RU_VOWELS:
            return i + 1
    return len(word)


def _r2_index(word: str) -> int:
    """R2 — область после второй последовательности «гласная+согласная»."""
    def region(start: int) -> int:
        i = start
        while i < len(word) - 1:
            if word[i] in _RU_VOWELS and word[i + 1] not in _RU_VOWELS:
                return i + 2
            i += 1
        return len(word)

    r1 = region(0)
    return region(r1) if r1 < len(word) else len(word)


class RussianStemmer:
    """Реализация русского стеммера Snowball."""

    @staticmethod
    def _try_endings(word: str, rv: int, endings: tuple[str, ...],
                     preceded_by: str = "") -> str | None:
        """Пытается отсечь одно из окончаний внутри области RV.

        ``preceded_by`` — если задано, окончанию должна предшествовать
        одна из перечисленных букв (для групп «после а/я»).
        """
        for end in sorted(endings, key=len, reverse=True):
            if not word.endswith(end):
                continue
            cut = len(word) - len(end)
            if cut < rv:
                continue
            if preceded_by:
                # согласно спецификации Snowball сама буква а/я в основе остаётся
                if cut == 0 or word[cut - 1] not in preceded_by:
                    continue
            return word[:cut]
        return None

    def stem(self, word: str) -> str:
        word = word.lower().replace("ё", "е")
        if len(word) <= 2:
            return word
        rv = _rv_index(word)
        r2 = _r2_index(word)

        # --- Шаг 1: деепричастие / возвратность + прилагательное/глагол/сущ.
        step1 = self._try_endings(word, rv, _PERFECTIVE_GERUND_1, "ая")
        if step1 is None:
            step1 = self._try_endings(word, rv, _PERFECTIVE_GERUND_2)
        if step1 is not None:
            word = step1
        else:
            refl = self._try_endings(word, rv, _REFLEXIVE)
            if refl is not None:
                word = refl
            adj = self._try_endings(word, rv, _ADJECTIVE)
            if adj is not None:
                word = adj
                part = self._try_endings(word, rv, _PARTICIPLE_1, "ая")
                if part is None:
                    part = self._try_endings(word, rv, _PARTICIPLE_2)
                if part is not None:
                    word = part
            else:
                verb = self._try_endings(word, rv, _VERB_1, "ая")
                if verb is None:
                    verb = self._try_endings(word, rv, _VERB_2)
                if verb is not None:
                    word = verb
                else:
                    noun = self._try_endings(word, rv, _NOUN)
                    if noun is not None:
                        word = noun

        # --- Шаг 2: отсечение конечного «и» в RV
        if word.endswith("и") and len(word) - 1 >= rv:
            word = word[:-1]

        # --- Шаг 3: словообразовательный суффикс в R2
        for end in _DERIVATIONAL:
            if word.endswith(end) and len(word) - len(end) >= r2:
                word = word[: len(word) - len(end)]
                break

        # --- Шаг 4: «нн» -> «н», превосходная степень, мягкий знак
        if word.endswith("нн"):
            word = word[:-1]
        else:
            sup = self._try_endings(word, rv, _SUPERLATIVE)
            if sup is not None:
                word = sup
                if word.endswith("нн"):
                    word = word[:-1]
        if word.endswith("ь"):
            word = word[:-1]
        return word


# --------------------------------------------------------------------------
#                    АНГЛИЙСКИЙ СТЕММЕР (Porter2 / Snowball)
# --------------------------------------------------------------------------

_EN_VOWELS = "aeiouy"
_DOUBLES = ("bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt")
_VALID_LI = "cdeghkmnrt"

_EXCEPTIONS = {
    "skis": "ski", "skies": "sky", "dying": "die", "lying": "lie", "tying": "tie",
    "idly": "idl", "gently": "gentl", "ugly": "ugli", "early": "earli",
    "only": "onli", "singly": "singl",
    "sky": "sky", "news": "news", "howe": "howe", "atlas": "atlas",
    "cosmos": "cosmos", "bias": "bias", "andes": "andes",
}
_EXCEPTIONS_STEP1A = {"inning", "outing", "canning", "herring", "earring",
                      "proceed", "exceed", "succeed"}


class EnglishStemmer:
    """Реализация английского стеммера Porter2 (Snowball English)."""

    # ---------- вспомогательные вычисления областей R1/R2 ----------
    @staticmethod
    def _r1r2(word: str) -> tuple[int, int]:
        def region(start: int) -> int:
            i = start
            while i < len(word) - 1:
                if word[i] in _EN_VOWELS and word[i + 1] not in _EN_VOWELS:
                    return i + 2
                i += 1
            return len(word)

        # Особые приставки согласно спецификации Porter2
        for prefix in ("gener", "commun", "arsen"):
            if word.startswith(prefix):
                r1 = len(prefix)
                break
        else:
            r1 = region(0)
        r2 = region(r1) if r1 < len(word) else len(word)
        return r1, r2

    @staticmethod
    def _is_short_syllable(word: str, i: int) -> bool:
        if i == 0:
            return (len(word) >= 2 and word[0] in _EN_VOWELS
                    and word[1] not in _EN_VOWELS)
        if i >= 1 and i + 1 < len(word):
            return (word[i] in _EN_VOWELS and word[i + 1] not in _EN_VOWELS
                    and word[i + 1] not in "wxY" and word[i - 1] not in _EN_VOWELS)
        return False

    def _is_short_word(self, word: str, r1: int) -> bool:
        return r1 >= len(word) and self._is_short_syllable(word, len(word) - 2)

    @staticmethod
    def _mark_y(word: str) -> str:
        """Заглавная Y обозначает согласный вариант буквы y."""
        if word.startswith("y"):
            word = "Y" + word[1:]
        out = list(word)
        for i in range(1, len(out)):
            if out[i] == "y" and out[i - 1] in _EN_VOWELS:
                out[i] = "Y"
        return "".join(out)

    # ------------------------------ шаги ------------------------------
    def stem(self, word: str) -> str:
        word = word.lower()
        if len(word) <= 2:
            return word
        if word in _EXCEPTIONS:
            return _EXCEPTIONS[word]
        word = word.replace("’", "'").strip("'")
        word = self._mark_y(word)
        r1, r2 = self._r1r2(word)

        word = self._step0(word)
        word = self._step1a(word)
        if word.replace("Y", "y") in _EXCEPTIONS_STEP1A:
            return word.replace("Y", "y")
        r1, r2 = self._r1r2(word)
        word = self._step1b(word, r1)
        word = self._step1c(word)
        r1, r2 = self._r1r2(word)
        word = self._step2(word, r1)
        r1, r2 = self._r1r2(word)
        word = self._step3(word, r1, r2)
        r1, r2 = self._r1r2(word)
        word = self._step4(word, r2)
        r1, r2 = self._r1r2(word)
        word = self._step5(word, r1, r2)
        return word.replace("Y", "y")

    @staticmethod
    def _step0(word: str) -> str:
        for suffix in ("'s'", "'s", "'"):
            if word.endswith(suffix):
                return word[: -len(suffix)]
        return word

    @staticmethod
    def _step1a(word: str) -> str:
        if word.endswith("sses"):
            return word[:-4] + "ss"
        if word.endswith(("ied", "ies")):
            return word[:-3] + ("i" if len(word) > 4 else "ie")
        if word.endswith(("us", "ss")):
            return word
        if word.endswith("s"):
            # удаляем -s, если в слове есть гласная перед предпоследней буквой
            if any(ch in _EN_VOWELS for ch in word[:-2]):
                return word[:-1]
        return word

    def _step1b(self, word: str, r1: int) -> str:
        for suffix in ("eedly", "eed"):
            if word.endswith(suffix):
                if len(word) - len(suffix) >= r1:
                    return word[: -len(suffix)] + "ee"
                return word
        for suffix in ("ingly", "edly", "ing", "ed"):
            if word.endswith(suffix):
                stem = word[: -len(suffix)]
                if not any(ch in _EN_VOWELS for ch in stem):
                    return word
                if stem.endswith(("at", "bl", "iz")):
                    return stem + "e"
                if stem.endswith(_DOUBLES):
                    return stem[:-1]
                if self._is_short_word(stem, self._r1r2(stem)[0]):
                    return stem + "e"
                return stem
        return word

    @staticmethod
    def _step1c(word: str) -> str:
        if len(word) > 2 and word[-1] in "yY" and word[-2] not in _EN_VOWELS:
            return word[:-1] + "i"
        return word

    @staticmethod
    def _step2(word: str, r1: int) -> str:
        pairs = (
            ("ization", "ize"), ("ational", "ate"), ("fulness", "ful"),
            ("ousness", "ous"), ("iveness", "ive"), ("tional", "tion"),
            ("biliti", "ble"), ("lessli", "less"), ("entli", "ent"),
            ("ation", "ate"), ("alism", "al"), ("aliti", "al"),
            ("ousli", "ous"), ("iviti", "ive"), ("fulli", "ful"),
            ("enci", "ence"), ("anci", "ance"), ("abli", "able"),
            ("izer", "ize"), ("ator", "ate"), ("alli", "al"),
            ("bli", "ble"), ("ogi", "og"), ("li", ""),
        )
        for suffix, repl in pairs:
            if not word.endswith(suffix):
                continue
            if len(word) - len(suffix) < r1:
                return word
            if suffix == "ogi":
                return word[:-1] if word[-4:-3] == "l" else word
            if suffix == "li":
                if len(word) > 2 and word[-3] in _VALID_LI:
                    return word[:-2]
                return word
            return word[: -len(suffix)] + repl
        return word

    @staticmethod
    def _step3(word: str, r1: int, r2: int) -> str:
        pairs = (("ational", "ate"), ("tional", "tion"), ("alize", "al"),
                 ("icate", "ic"), ("iciti", "ic"), ("ical", "ic"),
                 ("ful", ""), ("ness", ""))
        for suffix, repl in pairs:
            if word.endswith(suffix) and len(word) - len(suffix) >= r1:
                return word[: -len(suffix)] + repl
        if word.endswith("ative") and len(word) - 5 >= r2:
            return word[:-5]
        return word

    @staticmethod
    def _step4(word: str, r2: int) -> str:
        suffixes = ("ement", "ance", "ence", "able", "ible", "ment", "ant",
                    "ent", "ism", "ate", "iti", "ous", "ive", "ize", "al",
                    "er", "ic")
        for suffix in suffixes:
            if word.endswith(suffix) and len(word) - len(suffix) >= r2:
                return word[: -len(suffix)]
        if word.endswith("ion") and len(word) - 3 >= r2 and len(word) > 3 \
                and word[-4] in "st":
            return word[:-3]
        return word

    def _step5(self, word: str, r1: int, r2: int) -> str:
        if word.endswith("e"):
            if len(word) - 1 >= r2:
                return word[:-1]
            if len(word) - 1 >= r1 and not self._is_short_syllable(word[:-1], len(word) - 3):
                return word[:-1]
        if word.endswith("ll") and len(word) - 1 >= r2:
            return word[:-1]
        return word


_RU = RussianStemmer()
_EN = EnglishStemmer()


@functools.lru_cache(maxsize=200_000)
def stem(word: str, lang: str) -> str:
    """Возвращает основу слова для указанного языка (с кэшированием)."""
    if lang == "ru":
        return _RU.stem(word)
    if lang == "en":
        return _EN.stem(word)
    return word.lower()
