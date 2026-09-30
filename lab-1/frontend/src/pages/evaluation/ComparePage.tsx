import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDelta, fmtMetric } from "@/lib/format";
import { keys } from "@/lib/queries";
import { GroupedBarsWithCI } from "@/components/charts/GroupedBarsWithCI";
import { rankerColor, rankerLabel } from "@/components/charts/rankerColor";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";
import { metricLabel } from "@/lib/metricsRu";

export function ComparePage() {
  const ctx = useEvaluationContext();
  const runs = ctx.latestRuns;
  const selected = ctx.search.runs ?? runs.map((r) => r.id);
  const ordered = [ctx.baselineRun?.id, ...selected].filter((id, i, all): id is number => id !== undefined && all.indexOf(id) === i && runs.some((r) => r.id === id));
  const metric = ctx.search.metric;

  const compare = useQuery({
    queryKey: keys.eval.compare(ordered, metric),
    queryFn: () => api.eval.compare(ordered, metric),
    enabled: ordered.length >= 1,
  });

  const scalarMetrics = (ctx.metrics?.metrics ?? []).filter((m) => m.kind === "scalar" && m.edition !== "diagnostic");

  if (!ctx.collection) return <Skeleton lines={6} />;
  if (runs.length < 2) return <EmptyState title={t("Need at least two finished runs")} description={t("Run the rankers first.")} />;

  const toggle = (id: number) => {
    const next = ordered.includes(id) ? ordered.filter((x) => x !== id) : [...ordered, id];
    ctx.setSearch({ runs: next });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-caption text-text-secondary">{t("Runs")}</span>
        {runs.map((r) => (
          <button
            key={r.id}
            type="button"
            aria-pressed={ordered.includes(r.id)}
            onClick={() => toggle(r.id)}
            className={`rounded-pill border px-3 py-1 text-caption transition-colors ${ordered.includes(r.id) ? "border-accent bg-accent-soft text-accent" : "border-hairline text-text-secondary"}`}
          >
            <span aria-hidden className="mr-1.5 inline-block size-2 rounded-full align-middle" style={{ background: rankerColor(r.ranker) }} />
            {rankerLabel(r.ranker)}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-caption text-text-secondary">
          {t("Metric")}
          <select value={metric} onChange={(event) => ctx.setSearch({ metric: event.target.value })} className="rounded-pill border border-hairline bg-surface px-2 py-1 text-caption text-text" aria-label={t("Metric to compare")}>
            {scalarMetrics.map((m) => (
              <option key={m.key} value={m.key}>
                {metricLabel(m)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {compare.isPending && <Skeleton lines={6} />}
      {compare.isError && <ErrorState error={compare.error} onRetry={() => void compare.refetch()} />}
      {compare.data && (
        <>
          <div role="status" className="rounded-card border border-accent/30 bg-accent-soft p-4 text-[15px]">
            {t("Aligned on")} <strong className="tabular">{compare.data.topic_count}</strong> {t("topics scored by every selected run.")}{" "}
            <HelpTip anchor="glossary-intersection">
              {t("Means over different topic sets are not comparable. Every figure below is recomputed on the intersection; the stored mean and its own topic count are shown for reference.")}
            </HelpTip>
            {compare.data.rows.some((r) => r.dropped_topics > 0) && (
              <span className="ml-1 text-text-secondary">
                {compare.data.rows.filter((r) => r.dropped_topics > 0).map((r) => t("{ranker} lost {n}", { ranker: rankerLabel(r.ranker), n: r.dropped_topics })).join(", ")}.
              </span>
            )}
          </div>

          <Card title={t("Mean {metric} on the common topics", { metric: (() => { const spec = ctx.metrics?.metrics.find((m) => m.key === metric); return spec ? metricLabel(spec) : metric; })() })} padding="sm">
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("ranker")}</Th>
                    <Th numeric>{t("mean (intersection)")}</Th>
                    <Th numeric>{t("95% CI")}</Th>
                    <Th numeric>{t("Δ vs baseline")}</Th>
                    <Th numeric>{t("stored mean")}</Th>
                    <Th numeric>{t("stored num_q")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {compare.data.rows.map((row) => (
                    <tr key={row.run_id}>
                      <Td>
                        <span className="inline-flex items-center gap-2">
                          <span aria-hidden className="size-2.5 rounded-full" style={{ background: rankerColor(row.ranker) }} />
                          {rankerLabel(row.ranker)}
                          {row.run_id === compare.data?.baseline_run_id && <Badge>{t("baseline")}</Badge>}
                        </span>
                      </Td>
                      <Td numeric strong>
                        {fmtMetric(row.mean_on_intersection)}
                      </Td>
                      <Td numeric className="text-text-secondary">
                        [{fmtMetric(row.ci_low, 3)}, {fmtMetric(row.ci_high, 3)}]
                      </Td>
                      <Td numeric className={row.delta_vs_baseline && row.delta_vs_baseline > 0 ? "text-positive" : row.delta_vs_baseline && row.delta_vs_baseline < 0 ? "text-negative" : ""}>
                        {row.run_id === compare.data?.baseline_run_id ? "—" : fmtDelta(row.delta_vs_baseline)}
                      </Td>
                      <Td numeric className="text-text-secondary">
                        {fmtMetric(row.stored_mean)}
                      </Td>
                      <Td numeric className="text-text-secondary">
                        {row.stored_query_count}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
          </Card>

          <GroupedBarsWithCI
            metrics={[metric]}
            labels={Object.fromEntries((ctx.metrics?.metrics ?? []).map((m) => [m.key, metricLabel(m)]))}
            runs={compare.data.rows.map((row) => ({ ranker: row.ranker, values: { [metric]: { value: row.mean_on_intersection, ci_low: row.ci_low ?? null, ci_high: row.ci_high ?? null } } }))}
          />

          <Card title={t("Per topic")} subtitle={t("The value each run obtained on every common topic.")} padding="sm">
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th numeric>{t("topic")}</Th>
                    {compare.data.rows.map((row) => (
                      <Th key={row.run_id} numeric>
                        {rankerLabel(row.ranker)}
                      </Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compare.data.per_topic.map((t) => (
                    <tr key={t.query_id}>
                      <Td numeric>{t.ext_id ?? t.query_id}</Td>
                      {compare.data?.rows.map((row) => {
                        const value = t.values[String(row.run_id)];
                        const isBest = value !== undefined && value === Math.max(...Object.values(t.values));
                        return (
                          <Td key={row.run_id} numeric strong={isBest}>
                            {fmtMetric(value)}
                          </Td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </TableFrame>
            <div className="mt-2 text-right">
              <Button size="sm" variant="ghost" onClick={() => ctx.setSearch({ runs: undefined })}>
                {t("Reset selection")}
              </Button>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
