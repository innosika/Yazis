"""Literal dictionary records, so the pipeline can be tested without a database."""

from app.mt.glosses import content_words, parse_labels
from app.mt.lexicon import EntryRecord, LexiconIndex, SenseRecord, TranslationRecord
from app.mt.textnorm import normalise_headword, strip_stress

_next_id = [1000]


def _identifier() -> int:
    _next_id[0] += 1
    return _next_id[0]


def entry(headword: str, pos: str, *senses: tuple[str, list[str]]) -> EntryRecord:
    """Build an entry. Each sense is a (gloss, [russian forms]) pair."""
    records: list[SenseRecord] = []
    for index, (gloss, forms) in enumerate(senses):
        labels, definition = parse_labels(gloss)
        records.append(
            SenseRecord(
                id=_identifier(),
                idx=index,
                gloss=gloss,
                definition=definition,
                labels=tuple(labels),
                domain_scores={},
                translations=tuple(
                    TranslationRecord(_identifier(), position, form, strip_stress(form), False)
                    for position, form in enumerate(forms)
                ),
                definition_words=frozenset(content_words(definition)),
            )
        )
    norm = normalise_headword(headword)
    return EntryRecord(
        id=_identifier(),
        headword=headword,
        headword_norm=norm,
        pos=pos,
        ipa=None,
        word_count=len(norm.split()),
        is_user=False,
        senses=tuple(records),
    )


def index(*entries: EntryRecord) -> LexiconIndex:
    return LexiconIndex(list(entries))
