"""Reference data the interface needs: subject areas, tagsets, dictionary size."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_session
from app.mt.domains import DOMAINS, REGISTER_PENALTY
from app.mt.grammar import COMPOUND_PREPOSITIONS, DEP_CASE, PREPOSITIONS
from app.mt.tagset import OPENCORPORA, PENN, UPOS
from app.mt.tree import DEP_DESCRIPTIONS
from app.services import dictionary, tm

router = APIRouter(prefix="/meta", tags=["reference"])


@router.get("", summary="Everything the interface needs to describe itself")
async def meta(session: AsyncSession = Depends(get_session)) -> dict:
    return {
        "direction": {"source": "English", "target": "Russian", "code": "en-ru"},
        "variant": 1,
        "domains": [
            {
                "code": domain.code,
                "title": domain.title,
                "description": domain.description,
                "label_count": len(domain.labels),
                "keyword_count": len(domain.keywords),
            }
            for domain in DOMAINS.values()
        ],
        "modes": [
            {
                "code": "transfer",
                "title": "Transfer",
                "description": (
                    "Analyses the sentence, disambiguates each word, generates Russian "
                    "forms and rebuilds the structure. The system's main architecture."
                ),
            },
            {
                "code": "direct",
                "title": "Direct (word-for-word)",
                "description": (
                    "Substitutes the dictionary's first equivalent for every word, with no "
                    "disambiguation, no agreement and no reordering. The baseline."
                ),
            },
        ],
        "dictionary": await dictionary.dictionary_stats(session),
        "memory": await tm.stats(session),
        "thresholds": {
            "tm_exact": settings.tm_exact_threshold,
            "tm_fuzzy": settings.tm_fuzzy_threshold,
            "max_input_chars": settings.max_input_chars,
        },
        "enrichment": {"wiktionary_enabled": settings.enrich_wiktionary_enabled},
    }


@router.get("/tagsets", summary="Part-of-speech tags and their decoding")
async def tagsets() -> dict:
    return {
        "upos": [
            {"code": t.code, "name": t.name, "description": t.description, "examples": t.examples}
            for t in UPOS.values()
        ],
        "penn": [
            {"code": t.code, "name": t.name, "description": t.description, "examples": t.examples}
            for t in PENN.values()
        ],
        "opencorpora": [
            {"code": t.code, "name": t.name, "description": t.description, "examples": t.examples}
            for t in OPENCORPORA.values()
        ],
        "dependencies": [
            {"code": code, "description": description}
            for code, description in sorted(DEP_DESCRIPTIONS.items())
            if code
        ],
    }


@router.get("/rules", summary="The transfer rules, as data")
async def rules() -> dict:
    return {
        "prepositions": [
            {"english": english, "russian": russian or "— (case only)", "case": case}
            for english, (russian, case) in sorted(PREPOSITIONS.items())
        ],
        "compound_prepositions": [
            {"english": english, "russian": russian or "— (case only)", "case": case}
            for english, (russian, case) in sorted(COMPOUND_PREPOSITIONS.items())
        ],
        "dependency_cases": [
            {"dependency": dep, "case": case} for dep, case in sorted(DEP_CASE.items())
        ],
        "register_penalties": [
            {"label": label, "penalty": penalty}
            for label, penalty in sorted(REGISTER_PENALTY.items(), key=lambda i: -i[1])
        ],
    }
