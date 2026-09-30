import json, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e5e5ea", "grid.linewidth": 0.6, "axes.edgecolor": "#8e8e93",
                     "axes.titleweight": "bold", "figure.dpi": 200, "savefig.dpi": 200, "savefig.bbox": "tight"})

COLOR = {"vector": "#0071e3", "vector_idf": "#30b0c7", "vector_prf": "#a2845e", "bm25": "#ff9500", "fts": "#34c759", "semantic": "#5e5ce6", "hybrid": "#ff2d55"}
LABEL = {"vector": "Векторная (по заданию)", "vector_idf": "Векторная + IDF-запрос", "vector_prf": "Векторная + Роккио (PRF)", "bm25": "BM25", "fts": "PostgreSQL FTS", "semantic": "Семантическая", "hybrid": "Гибридная (RRF)"}
ORDER = ["vector", "vector_idf", "vector_prf", "bm25", "fts", "semantic", "hybrid"]
DASH = {"vector_idf": (0, (5, 2)), "vector_prf": (0, (2, 2))}

details = json.load(open("run_details.json"))
curves = json.load(open("curves.json"))
per_query = json.load(open("per_query.json"))
sig = json.load(open("significance.json"))
cmp_ = json.load(open("compare.json"))
tokens = [int(x) for x in open("token_counts.txt").read().split()]
crawl = json.load(open("crawl_jobs.json"))

def agg(r, key):
    for a in details[r]["aggregate"]:
        if a["metric_key"] == key: return a["value"]
    return float("nan")

# ---- fig: architecture ----
fig, ax = plt.subplots(figsize=(8.5, 4.6)); ax.axis("off"); ax.grid(False)
def box(x, y, w, h, title, sub="", fc="#f5f5f7", ec="#8e8e93"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=fc, ec=ec, lw=1))
    ax.text(x + w/2, y + h/2 + (0.18 if sub else 0), title, ha="center", va="center", fontsize=9.5, fontweight="bold")
    if sub: ax.text(x + w/2, y + h/2 - 0.22, sub, ha="center", va="center", fontsize=7.8, color="#3a3a3c")
def arrow(x1, y1, x2, y2, label="", style="-|>"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=12, lw=1, color="#3a3a3c"))
    if label: ax.text((x1+x2)/2, (y1+y2)/2 + 0.12, label, ha="center", fontsize=7.5, color="#3a3a3c")
ax.set_xlim(0, 12); ax.set_ylim(0, 6.2)
box(0.3, 4.3, 2.6, 1.3, "Браузер", "React 19 · TanStack Router\nRecharts · three.js · KaTeX", "#e8f1fd")
box(3.6, 4.3, 2.0, 1.3, "nginx", "SPA + прокси /api,\nSSE без буферизации")
box(6.4, 4.3, 3.0, 1.3, "API (FastAPI)", "поиск · корпус · краулер ·\nоценка · лаборатория", "#e8f1fd")
box(6.4, 2.2, 3.0, 1.3, "Worker (TaskIQ)", "обход сайтов · оценочные прогоны ·\nLLM-асессор · LSA", "#e8f1fd")
box(9.9, 4.3, 1.9, 1.3, "PostgreSQL 17", "pgvector,\nинвертированный индекс")
box(9.9, 2.2, 1.9, 1.3, "Redis 7", "очередь Streams,\npub/sub прогресса")
box(6.4, 0.2, 3.0, 1.3, "Ollama (профиль llm)", "локальная LLM-оценка\nрелевантности", "#fff4e5")
box(0.3, 2.2, 2.6, 1.3, "Интернет", "Wikipedia и др.\nrobots.txt, HTTP/2", "#f0fbf3")
arrow(2.9, 4.95, 3.6, 4.95, "HTTP"); arrow(5.6, 4.95, 6.4, 4.95, "/api"); arrow(9.4, 4.95, 9.9, 4.95, "SQL")
arrow(9.4, 2.85, 9.9, 2.85, "задачи"); arrow(7.9, 4.3, 7.9, 3.5, "", "<|-|>"); arrow(9.0, 3.5, 10.6, 4.3, "")
arrow(7.9, 2.2, 7.9, 1.5, "OpenAI API"); arrow(6.4, 2.85, 2.9, 2.85, "обход")
ax.text(7.2, 3.9, "прогресс\n(pub/sub → SSE)", fontsize=7, color="#3a3a3c", ha="right")
ax.text(10.2, 3.75, "SQL", fontsize=7.5, color="#3a3a3c")
fig.savefig("fig_architecture.png"); plt.close(fig)

# ---- fig: DB schema (compact) ----
fig, ax = plt.subplots(figsize=(10, 5.6)); ax.axis("off"); ax.grid(False); ax.set_xlim(0, 13.6); ax.set_ylim(0, 7.4)
W = 3.05
def table(x, y, name, cols, fc="#ffffff"):
    h = 0.3 * len(cols) + 0.5
    ax.add_patch(FancyBboxPatch((x, y), W, h, boxstyle="round,pad=0.02,rounding_size=0.1", fc=fc, ec="#8e8e93", lw=1))
    ax.text(x + W/2, y + h - 0.26, name, ha="center", va="center", fontsize=8.6, fontweight="bold", family="DejaVu Sans Mono")
    for i, c in enumerate(cols):
        ax.text(x + 0.12, y + h - 0.62 - 0.3*i, c, fontsize=6.9, family="DejaVu Sans Mono", va="center")
    return (x, y, W, h)
X = [0.3, 3.65, 7.0, 10.35]
d = table(X[0], 4.4, "document", ["id PK", "url UNIQUE, title, text", "published_at, source_domain", "content_hash, simhash", "vector_norm  ‖D‖", "embedding vector(384)"], "#e8f1fd")
p_ = table(X[1], 4.7, "posting", ["term_id FK, document_id FK", "term_frequency  N_dk", "weight_raw  A_i^j (1.6)", "weight_norm  w_dk", "positions int[]"], "#e8f1fd")
t = table(X[2], 5.0, "term", ["id PK, lemma UNIQUE", "document_frequency  N_k", "collection_frequency", "idf  B_i = log(N/N_k)"], "#e8f1fd")
cs = table(X[3], 5.3, "collection_stat", ["document_count  N", "term_count  D", "index_version, log_base"])
q = table(X[0], 0.3, "query (тема)", ["id PK, collection_id FK", "ext_id, title, narrative", "oracle_query, category", "is_judged, selected_at"])
pe = table(X[1], 2.6, "pool_entry", ["query_id, document_id", "source: run_union|oracle|", "        random_sample", "contributed_by jsonb"])
j = table(X[1], 0.3, "judgment", ["query_id, document_id", "assessor_id FK", "grade (5-балльная шкала)", "note, seconds_spent"])
qs = table(X[2], 2.6, "qrel_set → qrel", ["aggregation or|and", "threshold, query_count", "is_relevant, gain"])
r = table(X[2], 0.3, "eval_run → run_result", ["ranker, top_k, status, batch_id", "run_query_metric (метрика×тема)", "run_metric, run_curve", "significance_result"])
lsa = table(X[3], 2.6, "lsa_model / lsa_projection", ["basis Vᵀ, singular_values", "explained_variance_ratio", "x, y, z по документу"])
fs = table(X[3], 0.3, "feedback_session", ["original_query, α, β, γ", "iterations jsonb", "index_version"])
def link(a, b):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="-", color="#3a3a3c", lw=0.9))
link((X[0]+W, 5.6), (X[1], 5.6)); link((X[1]+W, 5.6), (X[2], 5.6))
link((X[0]+W/2, 4.4), (X[0]+W/2, 1.7)); link((X[0]+W, 1.0), (X[1], 1.0)); link((X[1]+W/2, 2.6), (X[1]+W/2, 1.7))
link((X[1]+W, 1.0), (X[2], 1.0)); link((X[2]+W/2, 2.6), (X[2]+W/2, 1.7)); link((X[1]+W, 3.3), (X[2], 3.3))
ax.text(X[0]+W+0.1, 5.7, "N", fontsize=7); ax.text(X[1]-0.25, 5.7, "N", fontsize=7); ax.text(X[1]+W+0.1, 5.7, "N", fontsize=7); ax.text(X[2]-0.25, 5.7, "1", fontsize=7)
ax.text(X[0]+W/2+0.08, 3.0, "1 : N (пул, оценки)", fontsize=6.8)
fig.savefig("fig_schema.png"); plt.close(fig)

# ---- fig: document length histogram ----
fig, ax = plt.subplots(figsize=(6.4, 3.0))
bins = np.logspace(math.log10(30), math.log10(20000), 24)
ax.hist(tokens, bins=bins, color="#0071e3", edgecolor="white", linewidth=0.6)
ax.set_xscale("log"); ax.set_xlabel("Длина документа, токенов (лог. шкала)"); ax.set_ylabel("Документов")
med = int(np.median(tokens)); ax.axvline(med, color="#ff9500", lw=1.4, ls="--"); ax.text(med*1.1, ax.get_ylim()[1]*0.9, f"медиана {med}", color="#b25000", fontsize=9)
ax.set_title(f"Распределение длин документов (N = {len(tokens)})", fontsize=10)
fig.savefig("fig_lengths.png"); plt.close(fig)

# ---- fig: crawl outcome ----
job = next(j for j in crawl if j["id"] == 5)
items = [("Проиндексировано", job["pages_indexed"], "#34c759")] + [(n, v, "#8e8e93") for n, v in sorted(job["skip_breakdown"].items(), key=lambda kv: -kv[1])]
ru = {"robots_disallowed": "Запрещено robots.txt", "duplicate_content": "Точный дубликат", "near_duplicate": "Почти дубликат (SimHash)", "http_error": "Ошибка HTTP", "too_short": "Слишком короткий текст"}
fig, ax = plt.subplots(figsize=(6.4, 2.6))
names = [ru.get(n, n) for n, _, _ in items][::-1]; vals = [v for _, v, _ in items][::-1]; cols = [c for _, _, c in items][::-1]
ax.barh(names, vals, color=cols, height=0.62)
for i, v in enumerate(vals): ax.text(v + 2, i, str(v), va="center", fontsize=9)
ax.set_xlabel("Страниц"); ax.set_title(f"Итог обхода: {job['pages_fetched']} загружено, {job['pages_indexed']} проиндексировано, {job['pages_skipped']} пропущено", fontsize=9.5)
ax.grid(axis="y", visible=False)
fig.savefig("fig_crawl.png"); plt.close(fig)

# ---- fig: MAP with CI + Rprec + nDCG grouped ----
rows = {r["ranker"]: r for r in cmp_["rows"]}
order = sorted(ORDER, key=lambda k: -rows[k]["mean_on_intersection"])
fig, ax = plt.subplots(figsize=(7.4, 3.6))
x = np.arange(len(order)); w = 0.26
map_v = [rows[k]["mean_on_intersection"] for k in order]
err = [[rows[k]["mean_on_intersection"] - rows[k]["ci_low"] for k in order], [rows[k]["ci_high"] - rows[k]["mean_on_intersection"] for k in order]]
ax.bar(x - w, map_v, w, color=[COLOR[k] for k in order], yerr=err, capsize=3, ecolor="#3a3a3c", label="MAP (с 95% бутстреп-ДИ)")
ax.bar(x, [agg(k, "rprec") for k in order], w, color=[COLOR[k] for k in order], alpha=0.6, label="R-точность", hatch="//", edgecolor="white")
ax.bar(x + w, [agg(k, "ndcg_10") for k in order], w, color=[COLOR[k] for k in order], alpha=0.35, label="nDCG@10", edgecolor="white")
for i, v in enumerate(map_v): ax.text(i - w, v + 0.06, f"{v:.3f}", ha="center", fontsize=7.5)
SHORT = {"vector": "Векторная\n(по заданию)", "vector_idf": "Векторная\n+ IDF-запрос", "vector_prf": "Векторная\n+ Роккио PRF", "bm25": "BM25", "fts": "PostgreSQL\nFTS", "semantic": "Семантическая", "hybrid": "Гибридная\n(RRF)"}
ax.set_xticks(x); ax.set_xticklabels([SHORT[k] for k in order], fontsize=7.5)
ax.set_ylim(0, 1.05); ax.set_ylabel("Значение метрики"); ax.grid(axis="x", visible=False)
ax.legend(fontsize=8, loc="upper right", frameon=False); ax.set_title("Коллекция известных документов, num_q = 30", fontsize=10)
fig.savefig("fig_map.png"); plt.close(fig)

# ---- fig: 11-point curves (two collections) ----
curves_t = json.load(open("curves_topical.json"))
fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.6), sharey=True)
for ax, data, title in ((axes[0], curves, "Известные документы (num_q = 30, R = 1)"), (axes[1], curves_t, "Тематическая, оценена частично (num_q = 5)")):
    for k in ORDER:
        if k not in data: continue
        pts = next(c for c in data[k] if c["curve_key"] == "iprec11")["points"]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=COLOR[k], lw=1.7, marker="o", ms=2.8, ls=DASH.get(k, "-"), label=LABEL[k])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02); ax.set_xlabel("Полнота"); ax.set_xticks(np.linspace(0, 1, 11)); ax.tick_params(labelsize=8)
    ax.set_title(title, fontsize=9)
axes[0].set_ylabel("Интерполированная точность"); axes[0].legend(fontsize=7, frameon=False, loc="lower left")
fig.suptitle("11-точечная кривая полноты/точности (методика TREC)", fontsize=10, fontweight="bold")
fig.savefig("fig_11pt.png"); plt.close(fig)

# ---- fig: P@k ----
fig, ax = plt.subplots(figsize=(6.4, 3.2))
for k in ORDER:
    pts = next(c for c in curves[k] if c["curve_key"] == "p_at_k")["points"]
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=COLOR[k], lw=1.8, marker="o", ms=3, ls=DASH.get(k, "-"), label=LABEL[k])
ax.axvline(5, color="#c7c7cc", ls=":", lw=1); ax.axvline(10, color="#c7c7cc", ls=":", lw=1)
ax.set_xlabel("k"); ax.set_ylabel("P@k"); ax.set_ylim(0, 1.02); ax.legend(fontsize=7.5, frameon=False)
ax.set_title("Точность на уровне k документов (R = 1 ⇒ P@k ≤ 1/k)", fontsize=10)
fig.savefig("fig_patk.png"); plt.close(fig)

# ---- fig: diverging ΔAP vector_idf vs vector ----
base = {q["query_id"]: q for q in per_query["vector"]}
rows_d = sorted([(q["ext_id"], q["metrics"]["ap"] - base[q["query_id"]]["metrics"]["ap"]) for q in per_query["vector_idf"] if q["query_id"] in base], key=lambda t: t[1])
fig, ax = plt.subplots(figsize=(6.4, 4.2))
ax.barh([str(e) for e, _ in rows_d], [d for _, d in rows_d], color=["#1d8a4e" if d >= 0 else "#d70015" for _, d in rows_d], height=0.7)
ax.axvline(0, color="#3a3a3c", lw=1); ax.set_xlim(-1, 1); ax.set_xlabel("ΔAP = AP(IDF-запрос) − AP(бинарный запрос)"); ax.set_ylabel("Тема (ext_id)")
wins = sum(1 for _, d in rows_d if d > 1e-9); losses = sum(1 for _, d in rows_d if d < -1e-9)
ax.set_title(f"Влияние IDF-взвешивания запроса по темам: {wins} лучше, {losses} хуже, {len(rows_d)-wins-losses} без изменений", fontsize=9.5)
ax.tick_params(axis="y", labelsize=7); ax.grid(axis="y", visible=False)
fig.savefig("fig_diverging.png"); plt.close(fig)

# ---- fig: significance heatmap (corrected p, Δ) ----
lab = {}
for s in sig:
    a = s["label_a"].split("#")[0]; b = s["label_b"].split("#")[0]
    lab[(a, b)] = (s["mean_difference"], s["p_value_corrected"]); lab[(b, a)] = (-s["mean_difference"], s["p_value_corrected"])
fig, ax = plt.subplots(figsize=(6.6, 4.6)); ax.grid(False)
n = len(ORDER); M = np.full((n, n), np.nan)
for i, a in enumerate(ORDER):
    for jx, b in enumerate(ORDER):
        if i != jx: M[i, jx] = lab[(a, b)][0]
im = ax.imshow(M, cmap="RdBu", vmin=-0.45, vmax=0.45)
for i, a in enumerate(ORDER):
    for jx, b in enumerate(ORDER):
        if i == jx: ax.text(jx, i, "—", ha="center", va="center", color="#8e8e93"); continue
        d, p = lab[(a, b)]
        mark = "‡" if p < 0.01 else ("†" if p < 0.05 else "")
        ax.text(jx, i, f"{d:+.3f}{mark}\np={p:.3f}", ha="center", va="center", fontsize=6.6, color="white" if abs(d) > 0.25 else "#1d1d1f")
short = {"vector": "Вект.", "vector_idf": "Вект.+IDF", "vector_prf": "Вект.+PRF", "bm25": "BM25", "fts": "FTS", "semantic": "Семант.", "hybrid": "Гибрид"}
ax.set_xticks(range(n)); ax.set_yticks(range(n)); ax.set_xticklabels([short[k] for k in ORDER], fontsize=8, rotation=30, ha="right"); ax.set_yticklabels([short[k] for k in ORDER], fontsize=8)
ax.set_title("Попарные различия MAP (строка − столбец); перестановочный тест, поправка Холма–Бонферрони\n† p < 0,05   ‡ p < 0,01", fontsize=8.5)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("ΔMAP", fontsize=8)
for s in ax.spines.values(): s.set_visible(False)
fig.savefig("fig_significance.png"); plt.close(fig)
print("charts done")
