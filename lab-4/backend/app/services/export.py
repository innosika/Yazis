"""Unicode `.txt` export of a translation run.

Requirement R9: «обеспечить сохранение и распечатку результатов перевода и упорядоченных по
частоте встречаемости в тексте списков слов и их переводов на выходной язык с грамматической
информацией в файл формата txt кодировки Unicode».

The file is written as UTF-8 **with a byte-order mark**. Plain UTF-8 would be the better
choice for a program to read, but this file is meant to be opened and printed by a person,
and a BOM is what makes Windows Notepad and Excel recognise Cyrillic instead of showing
mojibake. The tables are laid out with spaces rather than tabs for the same reason: the
result prints identically everywhere.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.mt.domains import get_domain
from app.mt.pipeline import TranslationResult

BOM = "﻿"
WIDTH = 96
MODE_TITLES = {
    "transfer": "transfer architecture (analysis, disambiguation, morphological generation)",
    "direct": "direct architecture (word-for-word substitution)",
}


def _width(text: str) -> int:
    """Display width of a string, ignoring the combining marks that take no column.

    The Russian side of the dictionary marks stress with a combining acute, so «учи́ться» is
    eight characters wide and seven columns wide. Padding by character count would shift
    every row that contains a stressed vowel, and this table is meant to be printed.
    """
    return sum(0 if unicodedata.combining(character) else 1 for character in text)


def _pad(text: str, columns: int) -> str:
    """Truncate to `columns` display columns, then pad to exactly that width."""
    out: list[str] = []
    used = 0
    for character in text:
        step = 0 if unicodedata.combining(character) else 1
        if used + step > columns:
            break
        out.append(character)
        used += step
    return "".join(out) + " " * (columns - used)


def build_txt(result: TranslationResult, title: str = "") -> str:
    """The complete export, as one Unicode string."""
    domain = get_domain(result.domain)
    stats = result.stats
    lines: list[str] = []

    def rule(character: str = "=") -> None:
        lines.append(character * WIDTH)

    def heading(text: str) -> None:
        lines.append("")
        rule()
        lines.append(text.upper())
        rule()
        lines.append("")

    lines.append(BOM + "MACHINE TRANSLATION REPORT")
    rule()
    lines.append(f"Document          {title or 'Untitled'}")
    lines.append(f"Generated         {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("Direction         English -> Russian")
    lines.append(f"Subject area      {domain.title} ({domain.description})")
    lines.append(f"Architecture      {MODE_TITLES.get(result.mode, result.mode)}")
    lines.append(f"Translation time  {result.duration_ms:.0f} ms")

    heading("1. Statistics")
    lines.append(f"Characters in the input text     {stats.characters}")
    lines.append(f"Sentences                        {stats.sentences}")
    lines.append(f"Words in the input text          {stats.words}")
    lines.append(f"  of which content words         {stats.content_words}")
    lines.append(f"Words translated                 {stats.translated_words}")
    lines.append(f"Words not found in the dictionary{stats.untranslated_words:>5}")
    lines.append(f"Dictionary coverage              {stats.coverage * 100:.1f}%")
    lines.append(f"Distinct lemmas                  {stats.unique_lemmas}")
    lines.append(f"Ambiguous words                  {stats.ambiguous_words}")
    lines.append(f"Tokens dropped by transfer rules {stats.dropped_tokens}")
    lines.append(f"Tokens inserted by transfer rules{stats.inserted_tokens:>5}")
    lines.append("")
    lines.append("Part-of-speech distribution of the input:")
    for tag, count in stats.pos_distribution.items():
        lines.append(f"  {tag:<8} {count}")

    heading("2. Translation")
    lines.append(result.target)
    lines.append("")
    lines.append("-" * WIDTH)
    lines.append("Sentence by sentence:")
    lines.append("")
    for sentence in result.sentences:
        lines.append(f"[{sentence.index + 1}] EN  {sentence.source.strip()}")
        lines.append(f"    RU  {sentence.target.strip()}")
        if sentence.tm_match:
            percent = sentence.tm_match["similarity"] * 100
            lines.append(
                f"    TM  {percent:.0f}% match from the translation memory"
                + (" (applied)" if sentence.tm_match["exact"] else "")
            )
        lines.append("")

    if result.direct_target:
        heading("3. Word-for-word translation, for comparison")
        lines.append(result.direct_target)
        word_list_number = 4
    else:
        word_list_number = 3

    heading(f"{word_list_number}. Words by frequency of occurrence, with grammatical information")
    lines.append(
        "Ordered by how often the word occurs in the input text. Counted over "
        "(lemma, part of speech) pairs,"
    )
    lines.append("so 'model' and 'models' form a single row.")
    lines.append("")
    header = (
        f"{'#':>3}  {'FREQ':>4}  {'ENGLISH LEMMA':<22} {'POS':<6} {'TAG':<5} "
        f"{'RUSSIAN':<26} GRAMMATICAL INFORMATION"
    )
    lines.append(header)
    lines.append("-" * max(WIDTH, len(header)))

    for position, row in enumerate(result.words, start=1):
        translation = row.translation_accented or row.translation
        if row.dropped_by_rule:
            translation = "— (dropped)"
        elif not row.translated:
            translation = "— (not in dictionary)"
        grammar = f"{row.tag_name}"
        if row.features:
            grammar += "; " + ", ".join(row.features)
        lines.append(
            f"{position:>3}  {row.count:>4}  {_pad(row.lemma, 22)} {row.upos:<6} "
            f"{row.tag:<5} {_pad(translation, 26)} {grammar}"
        )
        if row.gloss:
            lines.append(f"{'':>11}sense: {row.gloss[:78]}")
        if row.note and not row.translated:
            lines.append(f"{'':>11}note:  {row.note[:78]}")

    heading(f"{word_list_number + 1}. Part-of-speech tag decoding")
    lines.append("Every tag that occurs in the table above:")
    lines.append("")
    seen: set[str] = set()
    for row in result.words:
        if row.tag in seen:
            continue
        seen.add(row.tag)
        lines.append(f"  {row.tag:<6} {row.tag_name}")
        lines.append(f"  {'':<6} {row.tag_description}")
    lines.append("")
    lines.append("Universal part-of-speech tags:")
    seen.clear()
    for row in result.words:
        if row.upos in seen:
            continue
        seen.add(row.upos)
        lines.append(f"  {row.upos:<6} {row.pos_name} — {row.pos_description}")

    if result.oov:
        heading(f"{word_list_number + 2}. Words not found in the dictionary")
        lines.append("These were queued for the dictionary replenishment utility.")
        lines.append("")
        for mention in result.oov:
            lines.append(f"  {mention.occurrences:>3}x  {mention.lemma:<24} {mention.upos}")

    lines.append("")
    rule()
    lines.append("Dictionary: FreeDict eng-rus (CC BY-SA 3.0). Analysis: spaCy en_core_web_md.")
    lines.append("Russian morphology: pymorphy3 / OpenCorpora.")
    rule()

    return "\n".join(lines) + "\n"


def save_txt(content: str, filename: str) -> Path:
    """Write the export next to the other data, and return its path."""
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.exports_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def safe_filename(title: str, extension: str = "txt") -> str:
    stem = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in (title or "translation").strip().lower()
    ).strip("-")[:60]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stem or 'translation'}-{stamp}.{extension}"
