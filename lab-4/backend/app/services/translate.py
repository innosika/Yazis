"""Orchestration: everything the pipeline needs from the database, and back again.

The pipeline itself is synchronous and knows nothing about persistence. This layer fetches
the dictionary for the document, loads the sense locks for the active domain, runs the
pipeline, consults the translation memory for every sentence, queues the words that could
not be translated, and records the run.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import state
from app.db.models import Document
from app.mt.domains import get_domain
from app.mt.lexicon import build_index
from app.mt.pipeline import Pipeline, TranslationResult
from app.mt.tagset import explain_features, explain_penn, explain_upos
from app.mt.tree import tree_to_dict
from app.services import dictionary, tm

log = logging.getLogger(__name__)

# Trees are drawn one sentence at a time, but shipping them all with the translation saves a
# round trip per sentence the user clicks. A very long document is capped instead of
# refusing, because the assignment asks for the tree of a *chosen* sentence.
MAX_TREES = 120


async def translate(
    session: AsyncSession,
    text: str,
    domain: str = "general",
    mode: str = "transfer",
    include_direct: bool = True,
    use_memory: bool = True,
    save: bool = True,
    title: str = "",
) -> tuple[TranslationResult, dict]:
    """Translate `text` and return both the raw result and its API payload."""
    analyzer = state.analyzer()
    pipeline = Pipeline(analyzer, state.morph())

    analysis = analyzer.analyse(text)
    index = await build_index(session, analysis)
    overrides = await dictionary.load_overrides(session, domain)

    result = pipeline.run(
        text=text,
        index=index,
        domain=get_domain(domain),
        overrides=overrides,
        mode=mode,
        include_direct=include_direct,
    )

    matches: dict[int, tm.Match] = {}
    if use_memory and result.sentences:
        matches = await tm.best_matches(
            session, [sentence.source for sentence in result.sentences], domain
        )
        for index_, match in matches.items():
            result.sentences[index_].tm_match = {
                "id": match.id,
                "similarity": match.similarity,
                "source_text": match.source_text,
                "target_text": match.target_text,
                "domain_code": match.domain_code,
                "origin": match.origin,
                "exact": match.exact,
            }
        # An exact match is an approved human translation of this very sentence, so it
        # replaces the machine output rather than sitting next to it.
        for index_, match in matches.items():
            if match.exact:
                result.sentences[index_].target = match.target_text
                result.sentences[index_].edited = True
                await tm.count_hit(session, match.id)
        if any(match.exact for match in matches.values()):
            from app.mt.pieces import join_sentences

            result.target = join_sentences(result.sentences)

    if result.oov:
        await dictionary.record_oov(
            session,
            [
                (mention.lemma, mention.upos, mention.context, mention.occurrences)
                for mention in result.oov
            ],
        )

    document_id: int | None = None
    if save:
        document = Document(
            title=(title or _auto_title(text))[:300],
            source_text=text,
            domain_code=domain,
            mode=mode,
            stats=result.stats.as_dict(),
            duration_ms=result.duration_ms,
        )
        session.add(document)
        await session.commit()
        document_id = document.id

    return result, to_payload(result, document_id, len(matches))


def to_payload(result: TranslationResult, document_id: int | None, memory_hits: int) -> dict:
    """Serialise a result for the API, decoding every tag on the way out."""
    direct_by_index = {sentence.index: sentence.target for sentence in result.direct}

    return {
        "document_id": document_id,
        "domain": result.domain,
        "mode": result.mode,
        "source": result.source,
        "target": result.target,
        "direct_target": result.direct_target,
        "duration_ms": result.duration_ms,
        "stats": result.stats.as_dict(),
        "memory_hits": memory_hits,
        "sentences": [
            {
                "index": sentence.index,
                "source": sentence.source,
                "target": sentence.target,
                "stages": sentence.stages,
                "memory": sentence.tm_match,
                "direct": direct_by_index.get(sentence.index, ""),
                "pieces": [
                    {
                        "surface": piece.surface,
                        "kind": str(piece.kind),
                        "source_indices": list(piece.source_indices),
                        "source_text": piece.source_text,
                        "lemma": piece.lemma,
                        "tag": piece.tag,
                        "decoded": list(piece.decoded),
                        "case": piece.case,
                        "note": piece.note,
                    }
                    for piece in sentence.pieces
                ],
            }
            for sentence in result.sentences
        ],
        "words": [
            {
                "lemma": row.lemma,
                "upos": row.upos,
                "tag": row.tag,
                "count": row.count,
                "forms": row.forms,
                "translation": row.translation,
                "translation_accented": row.translation_accented,
                "gloss": row.gloss,
                "sense_index": row.sense_index,
                "sense_count": row.sense_count,
                "translated": row.translated,
                "pos_name": row.pos_name,
                "pos_description": row.pos_description,
                "tag_name": row.tag_name,
                "tag_description": row.tag_description,
                "features": row.features,
                "ambiguous": row.ambiguous,
                "from_user": row.from_user,
                "dropped_by_rule": row.dropped_by_rule,
                "note": row.note,
            }
            for row in result.words
        ],
        "tokens": [
            {
                "sentence": token.sentence,
                "index": token.index,
                "text": token.text,
                "lemma": token.lemma,
                "upos": token.upos,
                "tag": token.tag,
                "morph": token.morph,
                "dep": token.dep,
                "head": token.head,
                "translation": token.translation,
                "translation_accented": token.translation_accented,
                "gloss": token.gloss,
                "sense_count": token.sense_count,
                "ambiguous": token.ambiguous,
                "translated": token.translated,
                "dropped_by_rule": token.dropped_by_rule,
                "target_tag": token.target_tag,
                "target_decoded": token.target_decoded,
                "note": token.note,
                "features": explain_features(token.morph),
                "pos_name": explain_upos(token.upos).name,
                "tag_name": explain_penn(token.tag).name,
            }
            for token in result.tokens
        ],
        "trees": [
            {
                "sentence": sentence.index,
                "text": sentence.text,
                "root": _tree_of(result, sentence.index),
            }
            for sentence in result.analysis.sentences[:MAX_TREES]
        ],
        "ambiguities": [
            {
                "sentence": item.sentence,
                "token": item.token,
                "text": item.text,
                "lemma": item.lemma,
                "upos": item.upos,
                "pos_name": item.pos_name,
                "context": item.context,
                "margin": item.margin,
                "candidates": [
                    {
                        "sense_id": candidate.sense_id,
                        "translation_id": candidate.translation_id,
                        "entry_pos": candidate.entry_pos,
                        "sense_index": candidate.sense_index,
                        "gloss": candidate.gloss,
                        "labels": candidate.labels,
                        "translation": candidate.translation,
                        "translation_accented": candidate.translation_accented,
                        "alternatives": candidate.alternatives,
                        "score": candidate.score,
                        "signals": candidate.signals,
                        "selected": candidate.selected,
                        "locked": candidate.locked,
                    }
                    for candidate in item.candidates
                ],
            }
            for item in result.ambiguities
        ],
        "oov": [
            {
                "lemma": mention.lemma,
                "upos": mention.upos,
                "occurrences": mention.occurrences,
                "context": mention.context,
            }
            for mention in result.oov
        ],
    }


def _tree_of(result: TranslationResult, index: int) -> dict | None:
    node = result.sentence_tree(index)
    return tree_to_dict(node) if node else None


def _auto_title(text: str) -> str:
    first = " ".join(text.strip().split())[:60]
    return first or "Untitled"
