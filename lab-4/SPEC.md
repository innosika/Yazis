# Spec: Lab 4 — "Автоматический машинный перевод текстов" (variant 1)

Machine-translation workbench, **English → Russian**, subject areas **computer-science papers** and
**literary essays**. Rule-based MT (direct + transfer architectures) over a real bilingual dictionary
held in PostgreSQL, with full linguistic analysis exposed to the user.

## Objective

A user pastes or uploads an English text and gets:

1. its Russian translation, produced by a **transfer** MT pipeline (with a **direct** word-for-word
   mode for comparison);
2. word counts — total words, translated words, dictionary coverage;
3. grammatical information for every token — POS tag plus a plain-language decoding of that tag;
4. **Tab 1** — words ordered by frequency of occurrence, each with its Russian translation and
   grammatical information;
5. **Tab 2** — the syntactic parse tree of a chosen sentence;
6. a utility to **automatically extend and correct** the dictionary (DB tables);
7. `.txt` export in Unicode and a print view of the translation and the frequency list.

The interface is **English**, simple enough for a first-time user, with a `?` hint on every
non-obvious control and a Help page.

### Why rule-based and not a neural model

The assignment is about MT *principles*: direct vs transfer systems, dictionary-driven lexical
substitution, morphological generation, syntactic analysis. A neural black box would satisfy none of
the required outputs (per-word grammatical information, an editable dictionary, a traceable parse).
Every stage here is inspectable and every decision is explainable in the UI.

## Scope: required functionality

| # | Assignment requirement | Where it lives |
|---|---|---|
| R1 | Input: English natural-language text | `Translate` page — textarea, `.txt`/`.html` upload, sample texts |
| R2 | Count words in input | `stats.py` → stats bar |
| R3 | Count translated words | `stats.py` — tokens that resolved to a dictionary sense |
| R4 | POS tags **and their decoding** | `tagset.py` — UPOS + Penn Treebank tables with English descriptions |
| R5 | Output: Russian translation | `pipeline.py` (transfer) / `direct.py` (word-for-word) |
| R6 | Tab 1: frequency-ordered words + translations + grammar | `Words` tab |
| R7 | Tab 2: syntactic parse tree of a chosen sentence | `Tree` tab — SVG dependency tree |
| R8 | Utility for automatic replenishment/correction of the dictionary | `Dictionary` page + `enrich.py` |
| R9 | Save + print results to Unicode `.txt` | `export.py`, `GET /api/export/*`, print stylesheet |
| R10 | Simple, accessible interface | English UI, 4 top-level pages, `?` hints, Help page |

## Scope: additional features

**F1 — Translation memory with post-editing (CAT-style).**
Every sentence translation can be corrected inline. The correction is stored as a TM unit; when a
later sentence is identical or similar, the TM proposes the stored translation with a **match
percentage** (PostgreSQL `pg_trgm` trigram similarity, 100% = exact, ≥70% = fuzzy). Word-level
corrections are offered as dictionary patches, which is requirement R8 in its live form. TM is
searchable, exportable and importable.

**F2 — Domain-aware word-sense disambiguation.**
A domain selector (`Computer Science` / `Literature` / `General`) taken straight from variant 1.
Sense selection combines five explainable signals (see *Algorithms*); the Ambiguity panel lists every
candidate sense with its score breakdown and lets the user **lock** a sense for a domain, persisted in
`sense_override`. Demonstrable effect: `network` → «сеть» in CS vs «связи» in general text;
`character` → «персонаж» in Literature vs «символ» in CS; `computer` never resolves to the
rare-historical «вычислитель».

**Core demo (third selected item) — MT architecture comparison.**
`Trace` tab runs the same input through *direct* and *transfer* side by side and shows what each
pipeline stage changed: analysis → lexical transfer → WSD → morphological generation → syntactic
transfer → detokenisation. This is the methodology's own SMP classification made visible.

## Tech stack

| Layer | Choice | Version |
|---|---|---|
| Backend | Python, FastAPI, Uvicorn | 3.12, 0.115.x |
| ORM / migrations | SQLAlchemy (async) + asyncpg, Alembic | 2.0.x |
| Database | PostgreSQL with `pg_trgm` | 17 |
| English analysis | spaCy + `en_core_web_md` | 3.8.x |
| Russian morphology | pymorphy3 + `pymorphy3-dicts-ru` | 2.0.x |
| Dictionary data | FreeDict `eng-rus` 2025.11.23, CC-BY-SA 3.0 | 62 181 entries / 78 720 senses |
| Frontend | React, TypeScript, Vite, Tailwind CSS | 19, 5.7, 6, v4 |
| Serving | nginx (static + `/api` proxy) | alpine |
| Orchestration | Docker Compose + Makefile | compose v2 |

Ports are shifted off the defaults so the project never collides with labs 1–2 or anything already
running: **web 8090, API 8020, Postgres 5434**.

## Commands

```
make up            # build, start, migrate, seed the dictionary, wait for ready
make down          # stop and remove containers
make logs          # follow logs
make test          # pytest inside the backend container
make lint          # ruff + mypy (backend), eslint + tsc (frontend)
make seed          # re-seed the dictionary from data/dictionary/eng-rus.jsonl.gz
make dict-rebuild  # re-download FreeDict and regenerate the seed file
make psql          # psql shell into the database
make clean         # remove containers, volumes and images of this project
make info          # print URLs
```

## Project structure

```
backend/
  app/
    main.py                FastAPI app, lifespan (load spaCy, pymorphy3, warm caches)
    config.py              settings (pydantic-settings), paths, ports
    db/
      base.py              async engine, session factory
      models.py            SQLAlchemy models (see Data model)
      migrations/          Alembic
    mt/
      analysis.py          spaCy analysis -> Sentence/Token/DepTree dataclasses
      tagset.py            UPOS + Penn tag tables with human-readable decoding
      lexicon.py           dictionary lookup (lemma+POS, multiword units)
      wsd.py               sense selection, 5 signals, explainable breakdown
      grammar.py           rule tables: prepositions and their case government, dependency
                           role -> case, modals, pronouns, verb government, euphony
      transfer.py          syntactic transfer: drops, case assignment, agreement, reordering,
                           participles, passive voice
      morphgen.py          pymorphy3 generation + agreement propagation
      pieces.py            the output representation shared by both architectures, and the
                           Russian detokeniser (planned as detokenize.py)
      direct.py            direct (word-for-word) architecture
      pipeline.py          orchestration + per-stage trace
      stats.py             word counts, coverage, frequency table
      tree.py              parse-tree JSON for the frontend
    services/
      translate.py         request -> full TranslationResult
      tm.py                translation memory: fuzzy match, upsert, import/export
      enrich.py            automatic dictionary replenishment (3 sources)
      dictionary.py        CRUD over dictionary tables
      export.py            Unicode .txt / print HTML builders
    api/
      routes_translate.py  routes_dictionary.py  routes_tm.py
      routes_export.py     routes_meta.py  routes_health.py
    schemas/               pydantic request/response models
  scripts/
    build_dictionary.py    FreeDict TEI -> data/dictionary/eng-rus.jsonl.gz
    seed_dictionary.py     JSONL -> PostgreSQL (COPY-based bulk load)
  tests/                   pytest
frontend/
  src/
    pages/                 Translate, Dictionary, Memory, Help
    components/            results tabs, ParseTree, SentenceCard, WordsTab, StatsBar,
                           dictionary editor, OOV queue, UI primitives
    lib/                   api client, types, hash router, theme, async hooks
data/
  dictionary/              eng-rus.jsonl.gz (committed seed, 5 MB)
  samples/                 sample CS paper + literary essay texts
  exports/                 generated .txt files
```

The architecture notes the plan put in `docs/` live in README.md and in the Help page
instead, where the people who need them will actually find them.

## Data model

```sql
dict_entry(id, headword, headword_norm, pos, ipa, source, is_user, created_at, updated_at)
dict_sense(id, entry_id, idx, gloss, labels text[], domain_scores jsonb)
dict_translation(id, sense_id, idx, form_accented, form_plain, is_user)
sense_override(id, headword_norm, pos, domain_code, sense_id, note, created_at)
tm_unit(id, source_text, source_norm, target_text, domain_code, origin, hits, created_at, updated_at)
oov_term(id, lemma, pos, occurrences, status, suggestion jsonb, first_seen, last_seen)
document(id, title, source_text, domain_code, mode, stats jsonb, created_at)
```

Indexes: `dict_entry(headword_norm, pos)`, GIN `pg_trgm` on `tm_unit.source_norm`,
GIN on `dict_sense.labels`, `oov_term(occurrences desc)`.

## Algorithms

**Analysis.** spaCy `en_core_web_md`: sentence segmentation, tokenisation, lemmatisation, UPOS +
Penn tags, morphological features, dependency parse. Tag decoding comes from `tagset.py`, not from
spaCy's `explain`, so every tag also carries the grammatical categories the assignment asks for.

**Lexical transfer.** Lookup by `(lemma, mapped POS)` against `dict_entry`; multiword units
(`machine learning`, `in order to`) are matched greedily longest-first before single tokens. Failure
to resolve marks the token OOV — it stays in Latin script, is counted against coverage, and is logged
to `oov_term`.

**WSD (F2).** For each candidate sense, score =
`w1·domain_label_match + w2·domain_keyword_overlap + w3·lesk_overlap + w4·vector_similarity − w5·register_penalty + w6·sense_prior`.
- *domain_label_match* — Wiktionary topical labels parsed out of the gloss (`(computing, Internet)`)
  matched against the active domain's label set.
- *domain_keyword_overlap* — gloss content lemmas against the domain's term profile.
- *lesk_overlap* — simplified Lesk: gloss content lemmas ∩ sentence context lemmas.
- *vector_similarity* — max pairwise cosine between context and gloss content-word vectors.
- *register_penalty* — `archaic`, `obsolete`, `rare`, `historical`, `slang`, `dated` are penalised for
  academic prose.
- *sense_prior* — FreeDict sense order (first sense is usually the most frequent).
A `sense_override` row, when present, wins outright. The breakdown is returned to the UI.

**Morphological generation.** pymorphy3 parses the Russian lemma, then inflects it into the form the
transfer stage demands. Agreement is propagated over the dependency tree: adjectives and participles
take gender/number/case from their head noun, verbs take person/number from the subject, past-tense
verbs take the subject's gender.

**Syntactic transfer.** Rules driven by the dependency tree:
- `det` (articles) dropped — Russian has none;
- `nsubj` → nominative, `dobj`/`obj` → accusative, `iobj` → dative;
- `poss` + `case('s)` → genitive postposition; `prep(of)` + `pobj` → genitive, preposition dropped;
- other prepositions map to a Russian preposition with its governed case
  (`in`→в+prepositional, `to`→к+dative, `with`→с+instrumental, `by`→+instrumental, …);
- `aux(do)` support dropped; `aux(will)` → future; modal verbs → `должен`/`может`/`нужно` frames;
- copular `be` + predicate dropped in the present tense («The model is simple» → «Модель проста́»);
- word order: subject–verb–object preserved, `amod` kept pre-nominal, `nmod` moved post-nominal.

**Direct architecture.** Same lookup, first sense, no WSD, no agreement, no reordering, no drops —
the pos-for-pos baseline the methodology calls «пословный перевод».

**TM fuzzy match (F1).** Normalise (casefold, collapse whitespace, strip punctuation), then
`similarity(source_norm, :q)` over a `pg_trgm` GIN index; ≥0.98 exact, ≥0.70 fuzzy, ranked, top 5.

**Automatic dictionary replenishment (R8).** For every OOV lemma, three sources are tried in order
and a suggestion with a confidence is queued for one-click review:
1. **Wiktionary** translation tables (`{{t|ru|…}}`) via the MediaWiki API;
2. **derivational rules** — Greco-Latin suffix correspondences
   (`-tion`→`-ция`, `-ity`→`-ость`, `-ism`→`-изм`, `-logy`→`-логия`, `-ic`→`-ический`,
   `-al`→`-альный`, `-ous`→`-озный`, …) applied when the stem is already known;
3. **practical transcription** EN→RU for proper nouns and neologisms.
Nothing is written to the dictionary without user confirmation; corrections to existing entries are
the "correction" half of the utility.

## Code style

```python
async def lookup(session: AsyncSession, lemma: str, pos: Pos) -> list[Sense]:
    """Return every sense of `lemma` whose part of speech is compatible with `pos`.

    Senses keep their dictionary order: `idx` doubles as the frequency prior used by the
    disambiguator, so callers must not re-sort the result.
    """
    stmt = (
        select(DictSense)
        .join(DictEntry)
        .where(DictEntry.headword_norm == normalise(lemma))
        .where(DictEntry.pos.in_(POS_COMPATIBILITY[pos]))
        .order_by(DictSense.idx)
        .options(selectinload(DictSense.translations))
    )
    return [Sense.from_orm_row(row) for row in (await session.scalars(stmt))]
```

- Full type annotations; `from __future__ import annotations` not needed on 3.12.
- Linguistic data structures are frozen dataclasses; DB rows never leak past `services/`.
- Docstrings explain *why*, and every non-obvious linguistic rule cites the phenomenon it models.
- `ruff format` (line length 100), `ruff check`, `mypy --strict` on `app/mt`.
- React: function components, named exports, Tailwind utility classes, no CSS-in-JS.

## Testing strategy

`pytest` + `pytest-asyncio`, tests in `backend/tests/`:

- `test_analysis.py` — tagging and dependency structure of fixed sentences.
- `test_tagset.py` — every UPOS and Penn tag spaCy can emit has a decoding.
- `test_lexicon.py` — lookup, POS compatibility, multiword units.
- `test_wsd.py` — the domain cases above resolve correctly in both domains; overrides win.
- `test_morphgen.py` — case/number/gender/tense generation and agreement propagation.
- `test_transfer.py` — article drop, genitive of `of`, preposition government, copula drop.
- `test_pipeline.py` — golden translations for a CS paragraph and a literary paragraph.
- `test_stats.py` — word counts and coverage arithmetic.
- `test_tm.py` — exact and fuzzy match thresholds, hit counting.
- `test_enrich.py` — derivational rules and transcription (Wiktionary source mocked).
- `test_export.py` — `.txt` is valid UTF-8, contains both required sections.
- `test_api.py` — every route's contract, against a real Postgres service container.

Target: the `app/mt` package above 85% line coverage; API routes smoke-tested end to end.
Frontend: `tsc --noEmit` + eslint in CI; no unit tests for presentational components.

## Boundaries

- **Always:** run `make test` before declaring a task done; keep the UI English; keep every
  dictionary write behind explicit user confirmation; keep ports 8090/8020/5434.
- **Ask first:** adding a runtime dependency; changing the DB schema after the first migration;
  replacing the dictionary source; anything that sends user text to a third-party service.
- **Never:** commit secrets; translate with an external MT API (defeats the assignment);
  hard-code translations to make a test pass; delete or skip a failing test.

## Success criteria

1. `make up` on a clean machine reaches a working system; `make info` prints the URLs; no manual step.
2. Pasting the bundled CS sample and pressing Translate yields a Russian translation in < 3 s for a
   1 500-character text, with the stats bar showing total words, translated words and coverage %.
3. Dictionary coverage ≥ 90% of content-word tokens on both bundled samples.
4. Every token in the Words tab shows a POS tag **and** its decoding; the tab is sorted by frequency
   and re-sortable by any column.
5. The Tree tab draws the dependency tree of any chosen sentence, with token morphology beside it.
6. `network` translates «сеть» under Computer Science and «связи» under General; `character`
   translates «персонаж» under Literature and «символ» under Computer Science — shown with score
   breakdowns in the Ambiguity panel.
7. Editing a sentence translation and re-translating the same text returns it as a 100% TM match;
   a one-word variant returns it as a fuzzy match with a percentage.
8. An OOV word (e.g. `tokenizer`) appears in the OOV queue with an automatic suggestion, and
   accepting it makes the next translation of that word succeed.
9. Export produces a UTF-8 `.txt` containing the translation and the frequency-ordered list with
   grammatical information; the print view renders both on paper.
10. `make test` green; `make lint` clean.

## Open questions

None blocking. Deferred by choice: EN→RU for other variants' languages, PDF/DOCX input,
speech input.
