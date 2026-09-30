"""Automatic replenishment of the dictionary.

The assignment requires «утилита автоматического пополнения/корректировки полученного
словаря». Any dictionary snapshot has a permanent tail of words it does not contain -
"tokenizer", "postmodernism", "Vaswani" - and a translator that meets one can only report a
gap. This module proposes a filling for the gap automatically, from three sources tried in
descending order of reliability:

1. **Wiktionary.** The English Wiktionary's translation tables, read through the MediaWiki
   API. This is the same corpus the bundled dictionary was extracted from, but live and
   unfiltered, so it answers for words the snapshot missed. Optional: the system works with
   no network, and says so.

2. **Derivational correspondences.** Scientific English and Russian share a Greco-Latin
   layer with regular suffix correspondences - `-tion`/`-ция`, `-ism`/`-изм`,
   `-ic`/`-ический`, `-ization`/`-изация`. Applying them to a transcribed stem produces the
   Russian internationalism directly: "algorithmic" -> «алгоритмический». Each candidate is
   then checked against pymorphy3's dictionary, which is what separates a real Russian word
   from a plausible-looking string, and the confidence reported reflects that check.

3. **Practical transcription.** Always available, always applicable, lowest confidence.
   Right for names, and an honest last resort for everything else.

Nothing here writes to the dictionary. A suggestion is a proposal; `app.services.dictionary`
creates the entry only after the user has seen it and confirmed it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.mt.morphgen import MorphGenerator
from app.mt.translit import transcribe

log = logging.getLogger(__name__)

# Wiktionary marks translations with {{t|ru|…}} / {{t+|ru|…}}.
_WIKI_TRANSLATION = re.compile(r"\{\{t\+?\|ru\|([^|}]+)")
_WIKI_SECTION = re.compile(r"^==\s*([^=]+?)\s*==$", re.MULTILINE)

# English suffix -> Russian suffix, longest first so a specific rule wins over a general one.
DERIVATIONS: list[tuple[str, str]] = [
    ("ization", "изация"),
    ("isation", "изация"),
    ("ographic", "ографический"),
    ("ological", "ологический"),
    ("ology", "ология"),
    ("ography", "ография"),
    ("ometry", "ометрия"),
    ("onomy", "ономия"),
    ("izer", "изатор"),
    ("iser", "изатор"),
    ("ivity", "ивность"),
    ("ality", "альность"),
    ("ility", "ильность"),
    ("lation", "ляция"),
    ("ration", "рация"),
    ("ration", "рация"),
    ("ction", "кция"),
    ("ption", "пция"),
    ("ssion", "ссия"),
    ("ution", "уция"),
    ("ition", "иция"),
    ("ation", "ация"),
    ("sion", "зия"),
    ("tion", "ция"),
    ("ical", "ический"),
    ("istic", "истический"),
    ("ism", "изм"),
    ("ist", "ист"),
    ("ance", "анция"),
    ("ence", "енция"),
    ("ment", "мент"),
    ("ive", "ивный"),
    ("ous", "озный"),
    ("ary", "арный"),
    ("ory", "орный"),
    ("ize", "изировать"),
    ("ise", "изировать"),
    ("ify", "ифицировать"),
    ("ic", "ический"),
    ("al", "альный"),
    ("or", "ор"),
    ("er", "ер"),
]

# Which part of speech a derivation produces, so the created entry is tagged correctly.
SUFFIX_POS: dict[str, str] = {
    "изация": "n",
    "ология": "n",
    "ография": "n",
    "ометрия": "n",
    "ономия": "n",
    "изатор": "n",
    "ивность": "n",
    "альность": "n",
    "ильность": "n",
    "ляция": "n",
    "рация": "n",
    "кция": "n",
    "пция": "n",
    "ссия": "n",
    "уция": "n",
    "иция": "n",
    "ация": "n",
    "зия": "n",
    "ция": "n",
    "изм": "n",
    "ист": "n",
    "анция": "n",
    "енция": "n",
    "мент": "n",
    "ор": "n",
    "ер": "n",
    "ический": "adj",
    "ологический": "adj",
    "ографический": "adj",
    "истический": "adj",
    "ивный": "adj",
    "озный": "adj",
    "арный": "adj",
    "орный": "adj",
    "альный": "adj",
    "изировать": "v",
    "ифицировать": "v",
}


@dataclass(frozen=True, slots=True)
class Suggestion:
    lemma: str
    pos: str
    source: str
    confidence: float
    forms: list[str]
    explanation: str

    def as_dict(self) -> dict:
        return {
            "lemma": self.lemma,
            "pos": self.pos,
            "source": self.source,
            "confidence": self.confidence,
            "forms": self.forms,
            "explanation": self.explanation,
        }


UPOS_TO_DICT_POS = {
    "NOUN": "n",
    "PROPN": "pn",
    "VERB": "v",
    "ADJ": "adj",
    "ADV": "adv",
    "NUM": "numeral",
}


class Enricher:
    def __init__(self, morph: MorphGenerator) -> None:
        self.morph = morph
        self._client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def suggest(self, lemma: str, upos: str = "NOUN") -> Suggestion:
        """Best available proposal for one word."""
        pos = UPOS_TO_DICT_POS.get(upos, "n")

        if settings.enrich_wiktionary_enabled and upos != "PROPN":
            wiktionary = await self._from_wiktionary(lemma, pos)
            if wiktionary is not None:
                return wiktionary

        derived = self._from_derivation(lemma)
        if derived is not None:
            return derived

        return self._from_transcription(lemma, pos, upos)

    async def suggest_many(self, words: list[tuple[str, str]]) -> list[Suggestion]:
        out: list[Suggestion] = []
        for lemma, upos in words:
            try:
                out.append(await self.suggest(lemma, upos))
            except Exception:
                log.exception("suggestion failed for %s", lemma)
        return out

    # ------------------------------------------------------------------- source 1

    async def _from_wiktionary(self, lemma: str, pos: str) -> Suggestion | None:
        try:
            wikitext = await self._fetch_wikitext(lemma)
        except Exception as error:
            log.info("wiktionary unavailable for %s: %s", lemma, error)
            return None
        if not wikitext:
            return None

        forms = _unique(_clean_russian(match) for match in _WIKI_TRANSLATION.findall(wikitext))
        forms = [form for form in forms if form]
        if not forms:
            return None

        known = sum(1 for form in forms if self.morph.is_known(form))
        confidence = 0.9 if known else 0.7
        return Suggestion(
            lemma=lemma,
            pos=pos,
            source="wiktionary",
            confidence=confidence,
            forms=forms[:6],
            explanation=(
                f"Found {len(forms)} Russian equivalent(s) in the English Wiktionary's "
                f"translation table; {known} of them are in the Russian morphological "
                "dictionary."
            ),
        )

    async def _fetch_wikitext(self, lemma: str) -> str:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.wiktionary_timeout_s,
                headers={"User-Agent": settings.wiktionary_user_agent},
            )
        response = await self._client.get(
            settings.wiktionary_api,
            params={
                "action": "parse",
                "page": lemma,
                "prop": "wikitext",
                "format": "json",
                "formatversion": "2",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            return ""
        return payload.get("parse", {}).get("wikitext", "") or ""

    # ------------------------------------------------------------------- source 2

    def _from_derivation(self, lemma: str) -> Suggestion | None:
        word = lemma.lower()
        for english_suffix, russian_suffix in DERIVATIONS:
            if not word.endswith(english_suffix):
                continue
            stem = word[: -len(english_suffix)]
            if len(stem) < 3:
                continue
            candidate = transcribe(stem) + russian_suffix
            known = self.morph.is_known(candidate)
            # An unknown candidate is not necessarily wrong - «токенизатор» is correct and
            # absent from the dictionary - but it is a proposal to be checked, not an answer.
            if not known and len(DERIVATIONS) and english_suffix in {"er", "or", "al", "ic"}:
                # The short, ambiguous suffixes produce too much noise to offer unchecked.
                continue
            return Suggestion(
                lemma=lemma,
                pos=SUFFIX_POS.get(russian_suffix, "n"),
                source="derivation",
                confidence=0.75 if known else 0.4,
                forms=[candidate],
                explanation=(
                    f"Greco-Latin correspondence -{english_suffix} → -{russian_suffix} "
                    f"applied to the transcribed stem «{transcribe(stem)}». "
                    + (
                        "The result is in the Russian morphological dictionary."
                        if known
                        else "The result is not in the Russian dictionary - please check it."
                    )
                ),
            )
        return None

    # ------------------------------------------------------------------- source 3

    def _from_transcription(self, lemma: str, pos: str, upos: str) -> Suggestion:
        form = transcribe(lemma)
        is_name = upos == "PROPN"
        return Suggestion(
            lemma=lemma,
            pos="pn" if is_name else pos,
            source="transcription",
            confidence=0.6 if is_name else 0.3,
            forms=[form],
            explanation=(
                "Practical transcription of the English spelling. "
                + (
                    "Correct for a proper name."
                    if is_name
                    else "A last resort: check it before accepting."
                )
            ),
        )


def _clean_russian(raw: str) -> str:
    """Strip the stress marks and markup leftovers Wiktionary puts in a translation."""
    text = raw.replace("́", "").replace("[", "").replace("]", "").strip()
    text = re.sub(r"\s+", " ", text)
    return text if re.search(r"[а-яёА-ЯЁ]", text) else ""


def _unique(values) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen
