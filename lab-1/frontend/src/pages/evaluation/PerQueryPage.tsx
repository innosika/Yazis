import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { api, type QueryMetrics } from "@/lib/api";
import { fmtMetric } from "@/lib/format";
import { keys } from "@/lib/queries";
import { DivergingAPBars } from "@/components/charts/DivergingAPBars";
import { rankerColor, rankerLabel } from "@/components/charts/rankerColor";
import { Badge, GradeBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";
import { metricLabel } from "@/lib/metricsRu";

const COLUMNS = ["ap", "p_5", "p_10", "rprec", "ndcg_10", "num_rel", "num_rel_ret", "num_unjudged_ret"];

export function PerQueryPage() {
  const ctx = useEvaluationContext();
  const runs = ctx.latestRuns;
  const run = ctx.selectedRun;
  const baseline = ctx.baselineRun;
  const [sortKey, setSortKey] = useState<string>("ap");
  const [ascending, setAscending] = useState(true);
  const [open, setOpen] = useState<number | null>(null);

  const perQuery = useQuery({
    queryKey: keys.eval.runQueries(run?.id ?? 0),
    queryFn: () => api.eval.runQueries(run?.id ?? 0),
    enabled: run !== undefined,
  });
  const baselineQueries = useQuery({
    queryKey: keys.eval.runQueries(baseline?.id ?? 0),
    queryFn: () => api.eval.runQueries(baseline?.id ?? 0),
    enabled: baseline !== undefined && baseline.id !== run?.id,
  });

  const rows = useMemo(() => {
    const list = [...(perQuery.data ?? [])];
    list.sort((a, b) => {
      const av = sortKey === "ext_id" ? a.ext_id : (a.metrics[sortKey] ?? 0);
      const bv = sortKey === "ext_id" ? b.ext_id : (b.metrics[sortKey] ?? 0);
      return (ascending ? 1 : -1) * (av - bv || a.ext_id - b.ext_id);
    });
    return list;
  }, [perQuery.data, sortKey, ascending]);

  const specs = new Map((ctx.metrics?.metrics ?? []).map((s) => [s.key, s]));

  if (!ctx.collection) return <Skeleton lines={6} />;
  if (!run) return <EmptyState title={t("No finished runs")} description={t("Run the rankers first.")} />;

  const diverging = (() => {
    if (!baseline || baseline.id === run.id || !baselineQueries.data || !perQuery.data) return null;
    const base = new Map(baselineQueries.data.map((q) => [q.query_id, q]));
    return perQuery.data
      .filter((q) => base.has(q.query_id))
      .map((q) => ({ topic: q.title, ext_id: q.ext_id, delta: (q.metrics[ctx.search.metric] ?? 0) - (base.get(q.query_id)?.metrics[ctx.search.metric] ?? 0) }));
  })();

  const toggleSort = (key: string) => {
    if (sortKey === key) setAscending((v) => !v);
    else {
      setSortKey(key);
      setAscending(true);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-caption text-text-secondary">{t("Run")}</span>
        <SegmentedControl
          ariaLabel={t("Run to inspect")}
          size="sm"
          options={runs.map((r) => ({ value: String(r.id), label: rankerLabel(r.ranker), color: rankerColor(r.ranker) }))}
          value={String(run.id)}
          onChange={(value) => ctx.setSearch({ run: Number(value) })}
        />
        <span className="ml-auto text-caption text-text-secondary">
          {t("Baseline for differences:")}{" "}
          <select
            value={baseline?.ranker ?? ""}
            onChange={(event) => ctx.setSearch({ baseline: event.target.value })}
            className="rounded-pill border border-hairline bg-surface px-2 py-1 text-caption text-text"
            aria-label={t("Baseline ranker")}
          >
            {runs.map((r) => (
              <option key={r.id} value={r.ranker}>
                {rankerLabel(r.ranker)}
              </option>
            ))}
          </select>
        </span>
      </div>

      <Card
        title={t("Per-topic metrics — {ranker}", { ranker: rankerLabel(run.ranker) })}
        subtitle={t("Sorted by ascending average precision by default: the hardest topics first. Expand a row to see its top 10 with the judged grade of each document.")}
        padding="sm"
      >
        {perQuery.isPending && <Skeleton lines={8} />}
        {perQuery.isError && <ErrorState error={perQuery.error} compact />}
        {perQuery.data && (
          <TableFrame>
            <Table>
              <thead>
                <tr>
                  <Th numeric sortable sorted={sortKey === "ext_id" ? (ascending ? "asc" : "desc") : null} onSort={() => toggleSort("ext_id")}>
                    #
                  </Th>
                  <Th>{t("Topic")}</Th>
                  <Th>{t("Category")}</Th>
                  {COLUMNS.map((key) => (
                    <Th key={key} numeric sortable sorted={sortKey === key ? (ascending ? "asc" : "desc") : null} onSort={() => toggleSort(key)}>
                      {(() => { const spec = specs.get(key); return spec ? metricLabel(spec) : key; })()}
                    </Th>
                  ))}
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map((q) => (
                  <Row key={q.query_id} q={q} runId={run.id} open={open === q.query_id} onToggle={() => setOpen(open === q.query_id ? null : q.query_id)} />
                ))}
              </tbody>
            </Table>
          </TableFrame>
        )}
      </Card>

      {diverging && baseline && (
        <DivergingAPBars rows={diverging} metric={ctx.search.metric} rankerLabel={rankerLabel(run.ranker)} baselineLabel={rankerLabel(baseline.ranker)} />
      )}
    </div>
  );
}

function Row({ q, runId, open, onToggle }: { q: QueryMetrics; runId: number; open: boolean; onToggle: () => void }) {
  const drill = useQuery({
    queryKey: keys.eval.drilldown(runId, q.query_id),
    queryFn: () => api.eval.drilldown(runId, q.query_id, 10),
    enabled: open,
  });
  const cellClass = (key: string, value: number | undefined) =>
    key === "ap" && value !== undefined ? (value >= 0.7 ? "text-positive" : value < 0.3 ? "text-negative" : "") : "";
  return (
    <>
      <tr className="hover:bg-surface-sunken/60">
        <Td numeric>{q.ext_id}</Td>
        <Td>
          <button type="button" onClick={onToggle} aria-expanded={open} className="text-left font-medium text-text hover:text-accent">
            {q.title}
          </button>
        </Td>
        <Td>{q.category && <Badge>{t(q.category)}</Badge>}</Td>
        {COLUMNS.map((key) => (
          <Td key={key} numeric className={cellClass(key, q.metrics[key])}>
            {key.startsWith("num_") ? Math.round(q.metrics[key] ?? 0) : fmtMetric(q.metrics[key])}
          </Td>
        ))}
        <Td>
          <Button size="sm" variant="ghost" onClick={onToggle} aria-label={open ? t("Collapse") : t("Expand top 10")}>
            {open ? "▴" : "▾"}
          </Button>
        </Td>
      </tr>
      <AnimatePresence initial={false}>
        {open && (
          <tr>
            <td colSpan={COLUMNS.length + 4} className="hairline-b bg-surface-sunken/40 p-0">
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                <div className="p-4">
                  {drill.isPending && <Skeleton lines={4} />}
                  {drill.isError && <ErrorState error={drill.error} compact />}
                  {drill.data && (
                    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
                      <div>
                        <p className="mb-2 text-caption text-text-secondary">{t("Top 10 with judged grades")}</p>
                        <ol className="space-y-1">
                          {drill.data.top.map((d) => (
                            <li key={d.document_id} className="flex items-center gap-2 text-[14px]">
                              <span className="tabular w-6 text-right text-text-tertiary">{d.rank}</span>
                              <GradeBadge grade={d.is_judged || d.grade ? d.grade : null} compact />
                              <a href={d.url} target="_blank" rel="noreferrer noopener" className="truncate text-accent hover:underline">
                                {d.title}
                              </a>
                              <span className="tabular ml-auto text-caption text-text-tertiary">{fmtMetric(d.score)}</span>
                            </li>
                          ))}
                        </ol>
                      </div>
                      <div>
                        <p className="mb-2 text-caption text-text-secondary">
                          {t("Relevant documents (R = {r}) and where they ranked", { r: drill.data.relevant_total })}
                        </p>
                        <ul className="space-y-1">
                          {drill.data.relevant_documents.map((d) => (
                            <li key={d.document_id} className="flex items-center gap-2 text-[14px]">
                              <span className={`tabular w-10 text-right ${d.rank === 0 ? "text-negative" : "text-text-tertiary"}`}>{d.rank === 0 ? t("miss") : `#${d.rank}`}</span>
                              <a href={d.url} target="_blank" rel="noreferrer noopener" className="truncate text-accent hover:underline">
                                {d.title}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            </td>
          </tr>
        )}
      </AnimatePresence>
    </>
  );
}
