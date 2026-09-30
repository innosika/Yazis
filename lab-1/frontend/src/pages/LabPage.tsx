/**
 * Relevance Lab: the vector space in 3-D and Rocchio feedback with a human in the loop.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { LayoutGroup, motion } from "motion/react";
import { Suspense, lazy, useMemo, useState, type FormEvent } from "react";
import { api, type Feedback } from "@/lib/api";
import { fmtPct, fmtScore } from "@/lib/format";
import { keys } from "@/lib/queries";
import { labRoute } from "@/routes/router";
import { Formula } from "@/components/math/Formula";
import { FORMULAS } from "@/components/math/formulas";
import type { Mark, ScenePoint } from "@/components/three/VectorSpace";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { t } from "@/lib/i18n";

const VectorSpace = lazy(() => import("@/components/three/VectorSpace").then((m) => ({ default: m.VectorSpace })));

const EXAMPLES = ["vector space model", "web crawler", "punched card", "search engine history"];

export function LabPage() {
  const search = labRoute.useSearch();
  const navigate = useNavigate({ from: labRoute.fullPath });
  const [draft, setDraft] = useState(search.q);
  const [marks, setMarks] = useState<Record<number, Mark>>({});
  const [hovered, setHovered] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const [coefficients, setCoefficients] = useState({ alpha: 1.0, beta: 0.75, gamma: 0.15 });

  const space = useQuery({
    queryKey: keys.lab.space(search.q),
    queryFn: () => api.lab.space(search.q || undefined),
  });

  const apply = useMutation({
    mutationFn: () =>
      api.lab.feedback({
        ...(feedback ? { session_id: feedback.session_id } : {}),
        query: search.q,
        relevant: Object.entries(marks).filter(([, m]) => m === "rel").map(([id]) => Number(id)),
        non_relevant: Object.entries(marks).filter(([, m]) => m === "nonrel").map(([id]) => Number(id)),
        ...coefficients,
        limit: 100,
      }),
    onSuccess: (result) => {
      setFeedback(result);
      setViewing(null);
      setMarks({});
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setFeedback(null);
    setMarks({});
    setViewing(null);
    void navigate({ search: { q: draft.trim() } });
  };

  const data = space.data;

  // Scores for colouring: the latest feedback ranking if any, else the space's cosines.
  const scoreById = useMemo(() => {
    const map = new Map<number, number>();
    if (feedback) for (const entry of feedback.ranking) map.set(entry.document_id, entry.score);
    else if (data) for (const p of data.points) map.set(p.document_id, p.cosine);
    return map;
  }, [data, feedback]);

  const scale = useMemo(() => {
    if (!data) return 1;
    let max = 0;
    for (const p of data.points) max = Math.max(max, Math.abs(p.x), Math.abs(p.y), Math.abs(p.z));
    if (data.query) max = Math.max(max, Math.abs(data.query.x), Math.abs(data.query.y), Math.abs(data.query.z));
    return max || 1;
  }, [data]);

  const points: ScenePoint[] = useMemo(
    () => (data ? data.points.map((p) => ({ id: p.document_id, title: p.title, position: [p.x / scale, p.y / scale, p.z / scale], cosine: scoreById.get(p.document_id) ?? 0 })) : []),
    [data, scale, scoreById],
  );

  const history = feedback?.history ?? [];
  const shownIteration = viewing !== null ? history.find((h) => h.iteration === viewing) : null;
  const queryPoint: [number, number, number] | null = (() => {
    const raw = shownIteration?.projection ?? feedback?.query_point ?? (data?.query ? [data.query.x, data.query.y, data.query.z] : null);
    if (!raw || raw.length < 3) return null;
    const norm = Math.hypot(raw[0] ?? 0, raw[1] ?? 0, raw[2] ?? 0) || 1;
    return [((raw[0] ?? 0) / norm) * 0.9, ((raw[1] ?? 0) / norm) * 0.9, ((raw[2] ?? 0) / norm) * 0.9];
  })();
  const trail: Array<[number, number, number]> = (() => {
    const base = data?.query ? [[data.query.x, data.query.y, data.query.z]] : [];
    const all = [...base, ...history.map((h) => h.projection)].slice(0, -1);
    return all
      .filter((p) => p.length >= 3)
      .map((p) => {
        const norm = Math.hypot(p[0] ?? 0, p[1] ?? 0, p[2] ?? 0) || 1;
        return [((p[0] ?? 0) / norm) * 0.9, ((p[1] ?? 0) / norm) * 0.9, ((p[2] ?? 0) / norm) * 0.9] as [number, number, number];
      });
  })();

  const titles = useMemo(() => new Map((data?.points ?? []).map((p) => [p.document_id, { title: p.title, url: p.url }])), [data]);
  const ranking = feedback
    ? feedback.ranking
    : (data?.points ?? [])
        .filter((p) => p.rank != null)
        .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0))
        .map((p) => ({ rank: p.rank ?? 0, document_id: p.document_id, title: p.title, url: p.url, score: p.cosine, matched_lemmas: [] as string[], previous_rank: null as number | null }));

  const toggle = (id: number, mark: Mark) => setMarks((current) => (current[id] === mark ? Object.fromEntries(Object.entries(current).filter(([k]) => Number(k) !== id)) : { ...current, [id]: mark }));
  const marked = Object.keys(marks).length;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t("Relevance Lab")}
        title={t("The vector space, and a query that learns")}
        description={t("Every document is a point in the latent space of the term–document matrix (formula 1.7 decomposed by SVD). The query is a ray from the origin. Mark results relevant or not, apply Rocchio, and watch the ray move and the list re-sort.")}
        helpAnchor="help-lab"
      />

      <form onSubmit={submit} className="mb-6 flex flex-wrap items-center gap-2">
        <input type="search" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={t("Query, e.g. vector space model")} aria-label={t("Query")} className="min-w-64 flex-1 rounded-pill border border-hairline-strong bg-surface px-4 py-2 text-[15px] text-text" />
        <Button type="submit" variant="primary">
          {t("Project")}
        </Button>
        {!search.q && EXAMPLES.map((example) => (
          <Button key={example} size="sm" onClick={() => { setDraft(example); void navigate({ search: { q: example } }); }}>
            {example}
          </Button>
        ))}
      </form>

      {space.isError && <ErrorState error={space.error} onRetry={() => void space.refetch()} />}
      {space.isPending && <Skeleton lines={10} />}

      {data && (
        <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
          <div className="space-y-3">
            <div className="relative h-[520px] overflow-hidden rounded-card border border-hairline bg-surface shadow-sm">
              <Suspense fallback={<Skeleton lines={12} className="p-6" />}>
                <VectorSpace points={points} query={queryPoint} trail={trail} hovered={hovered} onHover={setHovered} marks={marks} onSelect={(id) => toggle(id, "rel")} />
              </Suspense>
              <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-2">
                <Badge>{t("{n} documents", { n: data.document_count })}</Badge>
                <Badge title={t("Fraction of the matrix's variance kept by three singular values")}>{t("this picture keeps {pct} of the variance", { pct: fmtPct(data.explained_variance_ratio, 1) })}</Badge>
                {data.query && <Badge tone="accent">{t("{k} of {n} query terms span the space", { k: data.query.terms_in_basis, n: data.query.lemmas.length })}</Badge>}
              </div>
              <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-2 text-caption text-text-secondary">
                <span>cos θ</span>
                <span className="h-2 w-28 rounded-pill" style={{ background: "linear-gradient(90deg, var(--relevance-0), var(--relevance-1), var(--relevance-2), var(--relevance-3))" }} aria-hidden />
                <span>0 → 1</span>
                <span className="ml-3 inline-block size-2.5 rounded-full bg-positive" aria-hidden /> {t("relevant")}
                <span className="ml-1 inline-block size-2.5 rounded-full bg-negative" aria-hidden /> {t("not relevant")}
              </div>
            </div>
            <p className="text-caption text-text-tertiary">
              {t("Hover a point for its angle in the picture (θ₃) and its true cosine in the full space. Singular values: {sv}. Drag to orbit, scroll to zoom. Click a point to mark it relevant.", { sv: data.singular_values.map((v) => v.toFixed(2)).join(", ") })}
            </p>
          </div>

          <div className="space-y-4">
            <Card
              title={t("Rocchio feedback")}
              subtitle={<Formula tex={FORMULAS.rocchio.tex} display />}
              actions={
                <HelpTip anchor="help-lab">
                  {t("α keeps the original query, β pulls it towards the centroid of the documents you marked relevant, γ pushes it away from the ones you marked not relevant. Each round starts from the previous vector, so the trajectory is cumulative and can be replayed below.")}
                </HelpTip>
              }
            >
              <div className="flex flex-wrap items-end gap-3">
                {(["alpha", "beta", "gamma"] as const).map((name) => (
                  <label key={name} className="block text-caption text-text-secondary">
                    {name === "alpha" ? "α" : name === "beta" ? "β" : "γ"}
                    <input type="number" step={0.05} min={0} max={10} value={coefficients[name]} onChange={(event) => setCoefficients({ ...coefficients, [name]: Number(event.target.value) })} className="mt-1 block w-20 rounded-pill border border-hairline bg-surface px-3 py-1 text-[14px] text-text" />
                  </label>
                ))}
                <Button variant="primary" loading={apply.isPending} disabled={marked === 0 || !search.q} onClick={() => apply.mutate()}>
                  {t("Apply Rocchio ({n} marked)", { n: marked })}
                </Button>
              </div>
              {apply.isError && <div className="mt-3"><ErrorState error={apply.error} compact /></div>}
              {feedback && (
                <div className="mt-4 space-y-2 text-caption">
                  <p className="text-text-secondary">
                    {t("Round {i}: the query now has {terms} terms ({added} added, {dropped} dropped), {cands} candidates.", { i: feedback.iteration, terms: feedback.query_terms.length, added: feedback.added_terms.length, dropped: feedback.dropped_terms.length, cands: feedback.total_candidates })}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {feedback.query_terms.slice(0, 24).map((term) => (
                      <Badge key={term.term_id} tone={term.is_original ? "accent" : "neutral"} title={`${t("weight")} ${term.weight.toFixed(3)}${term.previous_weight != null ? ` (${t("was")} ${term.previous_weight.toFixed(3)})` : ""}`}>
                        {term.lemma} <span className="tabular text-text-tertiary">{term.weight.toFixed(2)}</span>
                      </Badge>
                    ))}
                  </div>
                  {history.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-text-tertiary">{t("Replay:")}</span>
                      <button type="button" onClick={() => setViewing(null)} aria-pressed={viewing === null} className={`rounded-pill border px-2 py-0.5 ${viewing === null ? "border-accent text-accent" : "border-hairline text-text-secondary"}`}>
                        {t("latest")}
                      </button>
                      {history.map((h) => (
                        <button key={h.iteration} type="button" onClick={() => setViewing(h.iteration)} aria-pressed={viewing === h.iteration} className={`rounded-pill border px-2 py-0.5 ${viewing === h.iteration ? "border-accent text-accent" : "border-hairline text-text-secondary"}`} title={t("{r} relevant, {nr} non-relevant, {terms} terms", { r: h.relevant.length, nr: h.non_relevant.length, terms: h.term_count })}>
                        {t("round")} {h.iteration}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Card>

            <Card title={feedback ? t("Ranking after round {i}", { i: feedback.iteration }) : t("Ranking by the vector model")} subtitle={t("Mark documents, then apply. Rows re-sort in place as the query moves.")} padding="sm">
              {ranking.length === 0 ? (
                <EmptyState title={t("No matching documents")} description={t("None of the query words occurs in the collection.")} />
              ) : (
                <LayoutGroup>
                  <motion.ol layout className="max-h-[420px] space-y-1 overflow-y-auto pr-1">
                    {ranking.slice(0, 40).map((entry) => {
                      const mark = marks[entry.document_id];
                      const meta = titles.get(entry.document_id);
                      const moved = entry.previous_rank != null ? entry.previous_rank - entry.rank : 0;
                      return (
                        <motion.li
                          key={entry.document_id}
                          layout
                          transition={{ type: "spring", stiffness: 400, damping: 40 }}
                          onMouseEnter={() => setHovered(entry.document_id)}
                          onMouseLeave={() => setHovered(null)}
                          className={`flex items-center gap-2 rounded-panel px-2 py-1.5 text-[14px] ${hovered === entry.document_id ? "bg-surface-sunken" : ""}`}
                        >
                          <span className="tabular w-6 text-right text-text-tertiary">{entry.rank}</span>
                          <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: mark === "rel" ? "var(--positive)" : mark === "nonrel" ? "var(--negative)" : `color-mix(in srgb, var(--relevance-3) ${Math.round(Math.sqrt(entry.score) * 100)}%, var(--relevance-0))` }} />
                          <a href={meta?.url ?? entry.url} target="_blank" rel="noreferrer noopener" className="min-w-0 flex-1 truncate text-text hover:text-accent">
                            {(meta?.title ?? entry.title).replace(/ - Wikipedia$/, "")}
                          </a>
                          {moved !== 0 && <span className={`tabular text-caption ${moved > 0 ? "text-positive" : "text-negative"}`}>{moved > 0 ? `↑${moved}` : `↓${-moved}`}</span>}
                          <span className="tabular w-14 text-right text-caption text-text-secondary">{fmtScore(entry.score, 3)}</span>
                          <button type="button" aria-pressed={mark === "rel"} aria-label={t("Mark relevant")} onClick={() => toggle(entry.document_id, "rel")} className={`rounded-pill border px-2 text-caption ${mark === "rel" ? "border-positive bg-positive text-on-accent" : "border-hairline text-text-secondary hover:border-positive"}`}>
                            +
                          </button>
                          <button type="button" aria-pressed={mark === "nonrel"} aria-label={t("Mark not relevant")} onClick={() => toggle(entry.document_id, "nonrel")} className={`rounded-pill border px-2 text-caption ${mark === "nonrel" ? "border-negative bg-negative text-on-accent" : "border-hairline text-text-secondary hover:border-negative"}`}>
                            −
                          </button>
                        </motion.li>
                      );
                    })}
                  </motion.ol>
                </LayoutGroup>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
