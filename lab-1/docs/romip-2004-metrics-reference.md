# ROMIP'2004 Metrics — Implementation Reference

Spec for `backend/src/irs/eval/`. Source: **Приложение А. «Официальные метрики РОМИП'2004»**,
М. Агеев, И. Кураленок, Труды РОМИП'2004, стр. 142–150 — the `2004_romip_metrix.pdf` the lab
assignment cites.

> `romip.ru` serves a broken TLS chain — fetch over plain `http://`, not `https://`.

| Document | URL |
|---|---|
| Appendix A (2004) — **the lab's document** | http://romip.ru/romip2004/appendix_a_metrics.pdf |
| Standalone preprint (same text, reflowed) | http://romip.ru/docs/romip_metrics.pdf |
| Appendix A 2009 / 2010 (superset, fixes errors) | http://romip.ru/romip2009/20_appendix_a_metrics.pdf · http://romip.ru/romip2010/20_appendix_a_metrics.pdf |
| ROMIP'2004 organizers' report (pooling, scale, assessors) | http://romip.ru/romip2004/01_romip_overview.pdf |

---

## 1. The official 2004 metric list

**Search track — exactly these 8, and no others:**

1. полнота — recall
2. точность — precision
3. средняя точность — average precision
4. точность на уровне 5 документов — P@5
5. точность на уровне 10 документов — P@10
6. R-точность — R-precision
7. 11-точечный график полноты/точности по методике TREC
8. 11-точечный график, модифицированный вариант (**RIRES**) — **never defined in any edition**

Classification track: recall, precision, accuracy, error, F-measure.

**Actually reported in 2004** (organizers' report §6.3) — a narrower set; R-precision and the RIRES
curve were defined but not reported: `P@5, P@10, precision, average precision, recall, 11-pt TREC`.

**Not in the 2004 document** — these arrived in 2009/2010 and must be labelled as extensions, never
attributed to the lab's PDF: `bpref`, `bpref-10`, `DCG@n`, `nDCG@n`, `Graded MRR`, `ERR`, `PFound`,
`ReciprocalRank`.

Design consequence: the metric registry carries a `romip_edition` field (`2004` | `2009` | `2010`)
and the UI groups the official eight separately from the extensions. That distinction is itself
worth marks.

---

## 2. ROMIP conventions (all confirmed from source)

**Graded at collection time, binary at scoring time.** ROMIP moved to a 5-point scale deliberately,
because forcing a binary call makes assessors over-critical:

> «деление на "черное"/"белое" ставит перед асессором психологическую проблему и в таких случаях
> многие люди склонны давать чересчур критичные суждения»

| Enum | Russian | Grade |
|---|---|---|
| `VITAL` | Соответствующий (релевантный/витальный) | 3 |
| `RELEVANT_PLUS` | Скорее соответствующий (релевантный+) | 2 |
| `RELEVANT_MINUS` | Возможно соответствующий (релевантный−) | 1 |
| `NOTRELEVANT` | Не соответствующий | 0 |
| `CANTBEJUDGED` | Документ не может быть оценен | 0 |

All 8 official search metrics are then computed on a **binary** table derived from those grades.

**Two official qrel sets, from ≥2 assessors per pair:**
- **слабые требования (`or`)** — relevant if *at least one* assessment exceeds the threshold;
  "cannot judge" only if *all* say so.
- **сильные требования (`and`)** — non-relevant if *at least one* assessment fails the threshold.
- **Official 2004 threshold: `релевантный−`, i.e. grade ≥ 1** (a generous threshold).

Each (aggregation, threshold) pair yields a *different effective query set*, because queries left
with no relevant document are dropped. So `or_relevant-minus` and `and_relevant-minus` are not
comparable unless `num_q` is reported alongside.

**Zero-relevant queries are excluded:**

> «В TREC такие запросы не учитываются при вычислении метрик. В РОМИП принято такое же соглашение:
> запросы, для которых нет релевантных документов, не рассматриваются при вычислении метрик.»

Subtlety: *modern* trec_eval does **not** do this (its README records a 2006 correction — it now
ignores only queries with no relevance *information*). ROMIP's rule matches **old** trec_eval.
Implement ROMIP's rule as the default, expose it as a flag, and expect a deliberate discrepancy
against `pytrec_eval` on any query whose qrels are all zeros.

**Unjudged retrieved documents count as non-relevant.** 2004 has no bpref/infAP, so this is forced.
It penalises whichever ranker surfaces documents outside the pool — i.e. the newest one. Track
`num_unjudged_ret` per run and report bpref as a robustness check when it exceeds ~20% of the top 10.

**Pooling.** Pool = union of the top-N of every participating run; **depth 50** for both search
tracks. Runs submitted up to 100 links/query. **≥2 independent assessments** per query-document
pair. Assessor mutual agreement on the web classification track was **29% on average** (54% on the
gold subset) — a modest agreement figure is therefore defensible *and citable*.

**Anti-tuning query selection** — the best idea in the document:

> «участники получают избыточное число заданий, которое значительно превосходит число реально
> оцениваемых… нацелен на предотвращение настройки системы под конкретные задания»

Web ad-hoc 2004: **24,250 tasks issued, 67 judged** (48 new + 19 reused), chosen *after* all runs
were submitted, filtered for reasonable pool size, grammaticality and intelligibility.

**Averaging — and a genuine bug in the lab's PDF.** The *procedure* for the search track is:
compute each metric per query, then take the unweighted arithmetic mean over queries. By standard
terminology that is **macro-averaging**. But the editions label it inconsistently:

| Document | Label for "per-query then mean" | Search track text |
|---|---|---|
| `romip2004/appendix_a_metrics.pdf` (**the lab's**) | **микроусреднение** ← swapped | «только микроусреднение» |
| `docs/romip_metrics.pdf` | макроусреднение ← correct | «только микроусреднение» ← self-contradictory |
| `romip2010/…` | макроусреднение ← correct | «только макроусреднение» ← fixed |

→ **Implement macro-averaging**, and footnote the 2004 wording citing the 2010 correction. That is a
citable answer rather than an argument with the marker.

---

## 3. Formulas and edge cases

Notation: ranked list `d_1..d_n` (rank 1 best); grade `g(d) ∈ {0,1,2,3}`; binary
`rel(d) = [g(d) ≥ τ]`, official `τ = 1`; **`R` = number of relevant documents in the QRELS**
(never in the run); `N` = judged non-relevant in qrels.

### Set measures (`точность` / `полнота`)
Confusion matrix `a` = retrieved∧relevant, `b` = retrieved∧non-relevant, `c` = missed∧relevant.
`recall = a/(a+c)`, `precision = a/(a+b)`, `F = 2/(1/p + 1/r)`.

These are **set** measures over the *entire* submitted list — `set_P`/`set_recall` in trec_eval
terms, **not** P@k. Their value moves with run length, so always publish `top_k` beside them.

Appendix-stated F properties, useful as unit-test assertions: `0 ≤ F ≤ 1`; `F = 0` if `p = 0` or
`r = 0`; `F = p = r` when `p = r`; `min(p,r) ≤ F ≤ (p+r)/2`.

Accuracy in ROMIP used «общее число документов оценивавшихся хотя бы для одной категории» as the
denominator, not the whole collection («сказывается лишь на масштабе»).

### P@k
```
P@k = |{i ≤ k : rel(d_i)}| / k
```
**The denominator is always `k`**, even when fewer than `k` documents were returned. Stated in the
appendix directly and confirmed in trec_eval `m_P.c` (`rel_so_far / cutoffs[i]`). Never
`min(k, n_ret)`.

The appendix supplies its own critique, worth reproducing in the report: P@n is incomparable across
queries with different `R` — a perfect system scores `P@100 = 0.2` when `R = 20` but `0.3` when
`R = 30`. That is precisely the motivation for R-precision.

### R-Precision
`Rprec = P@R`. From `m_Rprec.c`: scan `min(n_ret, R)` positions, **divide by `R`**. A short run is
penalised as if the missing positions were non-relevant. Dividing by `num_to_look_at` is wrong.
`R = 0` → query excluded; empty run → 0.

### Average precision
The appendix's formulation, which pins the denominator unambiguously: for a query with `k` relevant
documents, `prec_rel(i) = P@pos(i)` if the `i`-th relevant document is found, and **`0` if it is
never found**. Then `AvgPrec = (1/k) · Σ prec_rel(i)`.

Equivalently `AP = (1/R) · Σ_{i: rel(d_i)} P@i`. Confirmed identical to `m_map.c`
(`sum / res_rels.num_rel`, guarded by `if (rel_so_far)` so an empty hit list scores 0).

Appendix-stated properties → four more golden tests: `AvgPrec ≤ recall`, with equality when every
relevant document sits at the very top; `AvgPrec ≈ precision·recall` when relevant documents are
spread uniformly; documents ranked below the last relevant one do not affect AP («отсекается "хвост"»).

The appendix cites Buckley & Voorhees SIGIR'00 for AP's stability against assessor variation — the
justification for making MAP the primary metric.

### 11-point interpolated precision/recall (TREC method)
For each `r_i ∈ {0.0, 0.1, …, 1.0}` and query `q_j`:
```
p(r_i, q_j) = 0                                    if r_i > recall(q_j)
              max_{n ≥ pos(r_i,q_j)} precision(n)   otherwise
Prec(r_i) = (1/N) · Σ_j p(r_i, q_j)
```
The only official 2004 metric that is inherently a **curve** — presumably why the lab demands графики.

**Worked example from the appendix — use verbatim as the golden test.** Collection of 20 documents,
4 relevant, all 20 returned, relevant at ranks **1, 2, 4, 15**. Interpolated precision:
**1.0** at recall 0.0–0.5; **0.75** at 0.6 and 0.7; **0.27** (= 4/15) at 0.8, 0.9, 1.0.

Traps:
- **The zeroing rule.** A query that never reaches recall `r_i` contributes **0** at that level, and
  that zero *is averaged in*. Confirmed in `m_iprec_at_recall.c`. Averaging over "only the queries
  that reached this level" is the most common 11-point bug and always flatters the system.
- **Recall level → document count.** *Verified 2026-09-03 against the trec_eval vendored by
  `pytrec_eval`:* it uses `(long)(level * R + 0.9)`, i.e. the appendix's **ceiling**, not `lround`
  as an earlier draft of this note claimed. Our `convention="romip"` (`math.ceil`) reproduces it
  everywhere except where floating point puts `level·R` just below an integer (0.7·3 =
  2.0999… → trec_eval needs 2 documents, `ceil` needs 3). `tests/unit/test_trec_eval_crossval.py`
  pins both facts.
- Compute the interpolation with a **reverse sweep carrying a running maximum**, as trec_eval does.
  A forward pass with look-ahead is O(n²) and easy to get subtly wrong.
- `11pt_avg` (mean of the 11 values) is a convenient scalar for the aggregate table.

### Metric #8 (RIRES) — undefined, so reconstruct and say so
Listed as official in every edition (2009/2010 rename it "ROMIP") but **never defined anywhere**;
§4 defines only the TREC variant and then goes to the bibliography. Implement the
**non-zeroing variant**: identical to TREC's, but at unreached recall levels average over only the
queries that did reach that level, reporting `n` per level. Plotting it against the TREC curve
*demonstrates* the effect of the zeroing convention, which is the deepest idea in the appendix.
Document it explicitly as a reconstruction.

### Extensions (label as ROMIP 2009/2010)

**bpref** — `Bpref = (1/R) Σ_r (1 − NonRelBefore(r)/R)`, unjudged documents *skipped* rather than
counted non-relevant. But `m_bpref.c` computes
`(1/R) Σ_r (1 − min(NonRelBefore(r), R) / min(N, R))` — **denominator `min(N,R)`, not `R`**. These
agree only when `N ≥ R`, and `N < R` is plausible in a small collection with a generous threshold.
bpref also changed incompatibly at trec_eval v8.0. ROMIP's **bpref-10** (denominator `10+R`) has
**no reference implementation** in modern trec_eval — unverifiable, so label it as such.

**DCG/nDCG** — ROMIP 2010: `DCG@n = Σ_p (2^g(p) − 1) / log2(2+p)`, `nDCG = DCG/Z`, cutoffs 5 and 10.
Two conventions to fix deliberately:
- *Gain*: trec_eval's `ndcg` uses **linear** gain (`m_ndcg.c` returns the relevance level), while
  gdeval, the Microsoft/Kaggle convention and ROMIP use **`2^g − 1`**. On a 0–3 scale these differ
  materially. Follow ROMIP (`2^g − 1`) and pass explicit gains when cross-checking.
- *Discount*: trec_eval uses `log2(i+2)` with `i` 0-based, i.e. `1/log2(1+rank)` — rank 1 gets
  discount 1. ROMIP's printed `log2(2+p)` with `p` 1-based gives rank 1 a discount of `1/log2 3`,
  almost certainly a 0-vs-1 indexing slip. Use `log2(1+rank)`, rank 1-based, and footnote it.

**ERR** (Chapelle et al. CIKM'09): `ERR = Σ_r (1/r) R_r Π_{i<r} (1−R_i)`, `R_i = (2^g_i − 1)/2^3`.

**PFound** (Гулин et al. РОМИП'2009): `PFound = Σ_r pLook(r)·pRel(r)` with
`pLook(r) = pLook(r−1)(1−pRel(r−1))(1−pBreak)`, `pBreak = 0.15`, `pLook(1) = 1`, and
`pRel(r) = 0.5·2^(g(r)−3)` for `g > 0`, else 0.

**ReciprocalRank** — ROMIP defines it via a *ruler*, not necessarily `1/x`: `1/pos` for document
search; TREC QA's `{1.0, 0.5, 0.33, 0.2, 0.1}` then 0; a ROMIP alternative `{1.0, 0.9, …, 0.1}`.
0 when no relevant answer is found.

---

## 4. Traps, ranked by likelihood of biting

**Tier 1 — silently wrong numbers.** All are special cases of *`R` must come from the qrels*:
1. MAP divides by `R` from qrels — not by relevant-retrieved, not by run length.
2. P@k divides by `k` — never by `min(k, n_ret)`.
3. R-Precision scans `min(n, R)` but divides by `R`.
4. 11-point: unreached recall levels contribute `0` to the mean, not "skip the query".
5. Zero-relevant queries excluded (ROMIP rule ≠ modern trec_eval). Always publish `num_q`.

**Tier 2 — conventions to choose explicitly and document.**
6. nDCG gain `2^g − 1` (ROMIP) vs linear (trec_eval).
7. DCG discount `log2(1+rank)`, rank 1-based; ROMIP's printed formula is off by one.
8. bpref denominator `min(N,R)` (trec_eval) vs `R` (ROMIP); bpref-10 unverifiable.
9. 11-point recall→count via `lround`.
10. `точность`/`полнота` are set measures — publish `top_k`.
11. micro/macro labels swapped in the 2004 PDF; implement macro.
12. Unjudged = non-relevant; track `num_unjudged_ret`.
13. Binary threshold: official is `or` @ `g ≥ 1`; also report `and` and check ranking stability
    (ROMIP's own results were threshold-sensitive: «при использовании слабых требований совпадают
    только первые два»).

**Tier 3 — methodology.**
14. Never compare MAP across different query subsets — align on the intersection, report its size.
15. Judging only your own top-k. Pooling across rankers is necessary but insufficient when all
    rankers share a lexical backbone — add an oracle run and a random sample.
16. Tuning on the judged queries makes reported numbers optimistic — use the oversample-then-select
    discipline, or hold out a tuning subset.
17. **Ties.** TF-IDF cosine produces exact ties (all-zero-overlap documents). Break them
    deterministically by `document_id` so runs are reproducible, and note it.
18. Sum per-query metrics in a stable (query-id-sorted) order so repeated runs are bit-identical.

---

## 5. Validation strategy

1. Export every run and qrel set to **TREC format** — run: `qid Q0 docid rank score runid`;
   qrels: `qid 0 docid rel`.
2. `pytrec_eval` vendors the actual NIST `trec_eval` C source as a submodule, so its numbers *are*
   trec_eval's. Needs a C toolchain (`build-essential`). It silently **ignores queries absent from
   qrels** — assert on `num_q` independently.
3. pytest asserting agreement to `1e-9` on `map`, `P_5`, `P_10`, `Rprec`, `recall_10`,
   `iprec_at_recall_*`, `bpref`, `ndcg_cut_10`, over both a synthetic fixture and the real collection.
4. Separately encode **the appendix's own worked example** (§3) and **the four AP properties** — these
   catch *convention* errors, which pytrec_eval agreement cannot.

Cross-implementation reference: <https://ir-measur.es/en/latest/measures.html> documents how each
backend parameterises `rel`, `cutoff`, `judged_only`, `gains`, `dcg`. Note `trectools` hard-codes
`rel=1`; `ranx` supports `log2`/`exp-log2` DCG but no custom gains.

---

## 6. Test collection plan for this lab

- **Author 60–80 queries, judge 25–30.** 25 is the practical floor for paired significance testing
  on AP (TREC ad-hoc used 50; below ~20 a single query flips the ranking). Then apply ROMIP's
  anti-tuning rule: freeze all runs *first*, then select the judged subset, and record the timestamp.
- **Query mix** must include short navigational queries, multi-word topical queries, and several with
  deliberate vocabulary mismatch (synonyms/paraphrase). Without the last group the semantic and
  hybrid rankers show no benefit and the comparison is vacuous.
- **Pool: depth 20** across all rankers (ROMIP used 50 with ~10 runs). Expect 30–60 unique documents
  per query, not `4·d`, because the lexical rankers overlap heavily. Plus two non-system sources:
  1. an **oracle run** (hand-built keyword/synonym query) to find relevant documents *no* ranker
     retrieved — the only way the recall denominator is not fiction;
  2. a **random sample** of 5–10 unjudged documents per query from outside the pool. If ~0% are
     relevant, that is *empirical evidence* of pool near-completeness rather than a hope.
- **Budget:** 25 queries × ~40 documents ≈ 1000 pairs at 15–25 s each ≈ 4–7 h per assessor. Drop to
  depth 10 if that is too much.
- **Hygiene:** present documents **blind and shuffled**, never in rank order or labelled by ranker.
  Use the 5-point scale verbatim. Two assessors on an overlapping ~30% subset; report agreement.
- **Publish:** `num_q`, pool depth, `num_unjudged_ret@10` per run, assessor agreement, and **both**
  qrel sets — and state plainly that recall is *pooled* recall.

## 7. Significance testing

Work on **paired per-query vectors** (AP, and separately nDCG@10 / P@10), restricted to queries
evaluated in *both* runs.

- **Permutation/randomization test — default.** For each of B ≥ 10,000 iterations flip the sign of
  each per-query difference with p = 0.5; `p` = fraction of iterations with mean |Δ| ≥ observed.
  Assumption-free and sound at n = 25.
- **Wilcoxon signed-rank** — safer than a t-test for bounded, skewed AP; ties/zeros are common at
  small n and cost power.
- **Paired t-test** — report it too, since readers expect it, but do not lean on it at n < 20.
- **Bootstrap** for **confidence intervals** on the aggregate (resample queries with replacement,
  B = 10,000, percentile CI) — this feeds the chart error bars. CIs communicate more than stars.

At n = 25–30 only **medium-to-large** effects are detectable — roughly a 15–25% relative MAP
difference. A 2% gap will not reach significance; say so rather than implying otherwise. Report n,
mean difference, CI and effect size (Cohen's `d_z` = mean(Δ)/sd(Δ)) beside every p-value. More
*queries* buys far more power than more judgments per query.

**Multiple comparisons:** 5 rankers = 10 pairs. Either designate TF-IDF cosine as the single
baseline (4 comparisons) or apply **Holm–Bonferroni** across all pairs, storing raw *and* corrected
p-values.
