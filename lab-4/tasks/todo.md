# Tasks

All complete. Verified by `make test` (176 tests), `make lint` (ruff, mypy --strict, eslint,
tsc) and a browser pass over every success criterion in SPEC.md.

- [x] T1 Scaffold: docker-compose (postgres/backend/frontend + healthchecks), Makefile, .env.example, .gitignore, git init
- [x] T2 DB: SQLAlchemy models, Alembic migration, pg_trgm extension, indexes
- [x] T3 Dictionary data: scripts/build_dictionary.py (FreeDict TEI -> JSONL.gz), scripts/seed_dictionary.py (bulk COPY, ~8 s for 62 009 entries)
- [x] T4 Analysis + tagset: spaCy wrapper, UPOS/Penn/OpenCorpora decoding tables
- [x] T5 Lexicon: dictionary lookup, POS compatibility map, multiword and hyphenated units
- [x] T6 WSD: domain profiles, six scoring signals, label taxonomy, overrides, explainable breakdown  [F2]
- [x] T7 Morphgen: pymorphy3 generation, agreement propagation, participles, animacy
- [x] T8 Transfer rules + direct baseline, including passive voice and aspect selection
- [x] T9 Pipeline: orchestration, per-stage trace, stats, frequency table, parse tree JSON
- [x] T10 API: /api/translate, /api/meta, /api/health
- [x] T11 TM: fuzzy match service, post-edit persistence, import/export, API  [F1]
- [x] T12 Dictionary service: CRUD, OOV queue, enrich.py (Wiktionary/derivation/transcription), API  [R8]
- [x] T13 Export: Unicode .txt builder with display-width column alignment, print stylesheet  [R9]
- [x] T14 Frontend shell: Vite+React+Tailwind v4, nginx, design system, api client
- [x] T15 Translate page: input, domain/mode controls, stats bar, five result tabs, alignment, post-edit
- [x] T16 Dictionary page: search, browse, edit, add, OOV queue with suggestions, locked senses
- [x] T17 Memory page: TM list, fuzzy-match probe, stats, import/export
- [x] T18 Help page: instructions, pipeline, tag reference, transfer-rule tables
- [x] T19 Samples + README + browser verification of all 10 success criteria

## Defects found during verification and fixed

1. Wiktionary link markup (`[[посадка|посадку]]`) reached 3% of translations verbatim.
2. Multiword units inherited the wrong syntactic role, so "neural network model" came out
   as «Нейронная сеть модель» instead of «модель нейронной сети».
3. `of` was dropped before its governed genitive was assigned, so "of the novel" lost its
   case entirely.
4. Coverage counted deliberately dropped articles as translation failures, understating it
   by roughly ten points.
5. `reloadMeta()` swapped the page for a loading skeleton, unmounting it and discarding the
   user's text whenever a sentence was saved to the memory.
6. An exact memory match replaced the sentence's target but the view still rendered the
   machine pieces, contradicting its own "reused" badge.
7. The replenishment queue seeded its rows from props once, so batch-proposed translations
   never appeared.
8. Do-support carried the tense, so "did not translate" became a present tense.
