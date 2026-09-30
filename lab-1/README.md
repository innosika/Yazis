# Information Retrieval System — Lab 1, variant 34

Vector search model (TF-IDF · cosine) over an English corpus acquired by **web crawling**, with the
**document-selection module** as the "AI element", and a full ROMIP-2004 quality evaluation. Backend
Python/FastAPI + PostgreSQL/pgvector + Redis + TaskIQ; frontend React 19 + Vite + Tailwind v4.

## One-minute start

```bash
make up            # build, start, seed the frozen 208-document corpus, build the index
make info          # prints the URLs
```

| Surface | URL |
|---|---|
| Interface | http://localhost:8080 |
| API docs | http://localhost:8010/api/docs |
| Readiness | http://localhost:8010/api/health/ready |

Ports are shifted off the defaults (Postgres 5433, Redis 6380, API 8010, web 8080) so the project
never collides with services already on the machine. `make help` or `./irs` lists every command.

## Defence walkthrough

The interface is in **Russian by default**; the RU / EN switch in the header changes every label,
tooltip, chart caption and the Help page. Every metric column carries a «?» tip with its Russian
name, definition and formula.


1. **Search** — type a query, pick a ranker (the starred *Vector model* is the mandated one; the others
   are baselines and two measured improvement proposals). Every result shows an **active link** and the
   **query words found** in the document. Press *Why this score?* for the glass box: the complete
   derivation of the cosine from `N_dk`, `N_k`, `N` through `B_k`, `A_k`, `w_dk`, the term-by-term
   scalar product, both norms and the final `r(D,Q)` — typeset with the assignment's own formulas.
2. **Corpus** — `N`, `D`, postings, index version; every document with its keywords by formula 1.6
   next to the normalised weight, so the two weightings can be compared. Add a document by URL
   (`AddDocumentToBase`) or delete one; the index is flagged stale until weights are recomputed.
3. **Crawl** — seeds, depth and page limits; live progress over server-sent events; the frontier with
   every skip reason (robots.txt, duplicate, near-duplicate by SimHash, too short, HTTP error) and
   per-stage timings; the crawler's structured log streamed live.
4. **Evaluation** (the required submenu) — collection and relevance-table selectors, then *Overview*
   (aggregate table with `num_q`, best-in-column, significance daggers, footnotes for degenerate
   metrics; grouped bars with bootstrap intervals), *Per topic* (sorted by AP, expandable top 10 with
   grades, diverging bars vs the baseline), *Curves* (11-point TREC curve with the non-zeroing
   reconstruction, raw sawtooth, P@k, grade distribution), *Comparison* (aligned on the topic
   intersection), *Significance* (permutation / Wilcoxon / paired t with Holm–Bonferroni, heatmap),
   *Collection & pool* (pipeline, pool provenance, LLM judging jobs, TREC exports), *Judge* (blind
   judging UI).
5. **Relevance Lab** — the term–document matrix decomposed by SVD and drawn as a 3-D point cloud; the
   query as a ray; documents coloured by cosine; mark results and apply **Rocchio** to watch the ray
   move and the list re-sort; replay the trajectory.
6. **Help** — the formulas, per-screen guidance, methodology, the metric registry, glossary and the
   third-party components.

## Evaluation pipeline

```
make evaluate                          # known-item collection (automatic, 30 topics)
make topics && make pool               # seed 46 hand-authored topics, build the pool (freezes the runs)
make topics-select                     # choose the 25 judged topics — refused before the pool exists
make llm-up && make llm-pull           # local LLM assessor (Ollama, compose profile `llm`, ~2 GB once)
make judge limit=3                     # smoke-test the assessor inline
# then start the full job from the interface (Evaluation → Collection & pool) or the API
make evaluate collection="topical (LLM-judged)"
```

The LLM assessor runs on the CPU and needs roughly 20–30 s per pair; ~800 pairs take several hours.
Any OpenAI-compatible endpoint can be substituted through `ASSESSOR_LLM_*` in `.env`.

## Development

```bash
make lint          # ruff + ruff format --check + mypy --strict
make test          # unit tests (no services): formulas, metrics, pooling, Rocchio, LSA, pytrec_eval cross-check
make test-all      # + integration tests against the live compose Postgres
cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
```

## Known limitations

- The topical collection is judged by a single LLM assessor, so the «or» and «and» relevance tables
  coincide and inter-assessor agreement is *not measured*.
- The known-item collection has one relevant document per topic: recall, bpref and set precision
  degenerate there and are shown as `n/a` with a footnote.
- The report generator (`make report`) is not implemented yet.
