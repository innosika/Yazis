# Implementation plan — Lab 4 MT workbench

## Dependency graph

```
T1 scaffold (compose, Makefile, .env, healthchecks)
 └─ T2 db (models, migration, pg_trgm)
     └─ T3 dictionary data (TEI->JSONL builder, bulk seeder)
         └─ T4 analysis + tagset (spaCy, POS decoding)      ← no DB dependency, can run parallel to T3
             └─ T5 lexicon (lookup, MWE)
                 ├─ T6 wsd (5 signals, overrides)           [F2]
                 └─ T7 morphgen (pymorphy3, agreement)
                     └─ T8 transfer (rules) + direct baseline
                         └─ T9 pipeline + stats + tree + trace
                             ├─ T10 api: translate, meta, health
                             ├─ T11 tm service + api                [F1]
                             ├─ T12 dictionary CRUD + enrich + api  [R8]
                             └─ T13 export (.txt, print)            [R9]
                                 └─ T14 frontend shell + design system
                                     ├─ T15 Translate page + results tabs (Translation/Words/Tree/Trace)
                                     ├─ T16 Dictionary page + OOV queue
                                     ├─ T17 Memory page
                                     └─ T18 Help page
                                         └─ T19 samples, README, end-to-end verification in browser
```

## Build order and rationale

Vertical slice first: T1–T9 give a translating pipeline testable from pytest with no UI. T10 exposes
it. T11–T13 are independent services that hang off the same pipeline result. The frontend (T14–T18)
consumes a frozen API contract, so it is built last and in one pass.

## Risks

| Risk | Mitigation |
|---|---|
| spaCy + model download makes the image slow to build | model installed in a cached Docker layer before `COPY app`; ~55 MB |
| Seeding 62k entries / 78k senses is slow | `COPY FROM STDIN` bulk load, one transaction; target < 30 s |
| pymorphy3 cannot inflect a dictionary lemma (multiword, phrase) | fall back to the uninflected lemma and mark the token as "not inflected" in the trace, never crash |
| Transfer rules produce word salad on hard sentences | rules are additive and each is unit-tested; direct mode is always available as the honest baseline |
| Wiktionary API unreachable offline | enrichment degrades to derivational rules + transcription; UI states which source answered |
| Accented dictionary forms (`сеть` vs `се́ть`) break pymorphy3 | store both `form_accented` (display) and `form_plain` (analysis); always analyse the plain form |

## Verification checkpoints

- After T3: `SELECT count(*) FROM dict_sense` = 78 720; lookup of `network` returns both senses.
- After T9: `make test` green; golden translation of the CS sample paragraph is stable.
- After T13: every success criterion 1–3, 9 verifiable by curl.
- After T19: criteria 4–8, 10 verified in the browser.
