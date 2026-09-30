"""Normalisation shared by the dictionary loader, the lookup path and the memory matcher.

Everything the dictionary is keyed by and everything the translator looks up passes through
`normalise_headword`, so the two can never drift apart.
"""

import re
import unicodedata

_WS = re.compile(r"\s+")
# Wiktionary link markup, which survives into a small fraction of the extracted
# translations: [[lemma|surface form]] or [[word]].
_WIKI_LINK = re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]")
_WIKI_LEFTOVER = re.compile(r"[\[\]{}]|'{2,}")
_TRIM = re.compile(r"^[^\w'-]+|[^\w'-]+$", re.UNICODE)
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_COMBINING_STRESS = ("́", "̀")


def strip_stress(text: str) -> str:
    """Remove the combining acute/grave the Russian side of the dictionary marks stress with."""
    for mark in _COMBINING_STRESS:
        text = text.replace(mark, "")
    return text


def clean_translation(text: str) -> str:
    """Remove the wiki markup that reaches ~3% of the extracted Russian equivalents.

    The source dictionary is extracted from Wiktionary, and some translations keep its link
    syntax: «[[самовольный|самовольная]] [[отлучка]]». The displayed text is the part after
    the pipe, or the whole link when there is none, so unwrapping the links yields
    «самовольная отлучка». Without this the markup appears verbatim in the translation, which
    is both wrong and the most visible kind of wrong.
    """
    text = _WIKI_LINK.sub(r"\1", text or "")
    text = _WIKI_LEFTOVER.sub("", text)
    return _WS.sub(" ", text).strip()


def normalise_headword(text: str) -> str:
    """Dictionary key for an English word or multiword unit.

    Case-folded, NFC-composed, stress-free, whitespace-collapsed, with surrounding
    punctuation trimmed. Hyphens and apostrophes survive, because "e-mail" and "o'clock"
    are headwords in their own right.
    """
    text = unicodedata.normalize("NFC", strip_stress(text or ""))
    text = text.replace("’", "'").replace("‘", "'")
    text = _WS.sub(" ", text).strip().casefold()
    return _TRIM.sub("", text)


def normalise_segment(text: str) -> str:
    """Translation-memory key for a sentence.

    Punctuation and case are dropped so that "The model is simple." and "the model is
    simple" are the same unit, while trigram similarity still sees the words.
    """
    text = unicodedata.normalize("NFC", (text or "").replace("’", "'"))
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip().casefold()
