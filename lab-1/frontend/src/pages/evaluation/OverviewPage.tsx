import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, type MetricSpec, type RunDetail } from "@/lib/api";
import { fmtInt, fmtMetric } from "@/lib/format";
import { keys } from "@/lib/queries";
import { GroupedBarsWithCI } from "@/components/charts/GroupedBarsWithCI";
import { rankerColor, rankerLabel } from "@/components/charts/rankerColor";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { editionLabel } from "@/lib/editions";
import { MetricHeader } from "@/features/evaluation/MetricHeader";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";
import { metricLabel, translateCaveat } from "@/lib/metricsRu";

const SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹";
const sup = (n: number) => String(n).split("").map((d) => SUPERSCRIPTS[Number(d)] ?? d).join("");

export function OverviewPage() {
  const ctx = useEvaluationContext();
  const runs = ctx.latestRuns;

  const details = useQueries({
    queries: runs.map((run) => ({ queryKey: keys.eval.run(run.id), queryFn: () => api.eval.run(run.id) })),
  });
  const runIds = runs.map((r) => r.id);
  const significance = useQuery({
    queryKey: keys.eval.significance(runIds, ctx.search.metric, "permutation"),
    queryFn: () => api.eval.significance(runIds, ctx.search.metric, "permutation"),
    enabled: runIds.length >= 2,
  });

  const loaded = details.map((d) => d.data).filter((d): d is RunDetail => d !== undefined);
  const specs = ctx.metrics?.metrics ?? [];
  const order = ctx.metrics?.primary_order ?? [];
  const specByKey = new Map(specs.map((s) => [s.key, s]));
  const columns: MetricSpec[] = order.map((k) => specByKey.get(k)).filter((s): s is MetricSpec => s !== undefined);

  const caveats = loaded[0]?.caveats ?? [];
  const degenerate = caveats.filter((c) => c.kind === "degenerate");
  const footnote = new Map(degenerate.map((c, i) => [c.metric_key, i + 1]));
  const notes = caveats.filter((c) => c.kind === "annotate");

  const best = useMemo(() => {
    const map = new Map<string, number>();
    for (const spec of columns) {
      const values = loaded.map((d) => d.aggregate.find((a) => a.metric_key === spec.key)?.value).filter((v): v is number => v !== undefined);
      if (values.length) map.set(spec.key, spec.higher_is_better ? Math.max(...values) : Math.min(...values));
    }
    return map;
  }, [columns, loaded]);

  const baseline = ctx.baselineRun;
  const daggers = new Map<number, string>();
  for (const s of significance.data ?? []) {
    const other = s.run_a_id === baseline?.id ? s.run_b_id : s.run_b_id === baseline?.id ? s.run_a_id : null;
    if (other == null) continue;
    const p = s.p_value_corrected ?? s.p_value;
    daggers.set(other, p < 0.01 ? "‡" : p < 0.05 ? "†" : "");
  }

  if (!ctx.collection) return <Skeleton lines={6} />;
  if (runs.length === 0) {
    return (
      <EmptyState
        title={t("No finished runs for this relevance table")}
        description={t("Use “Run all rankers” above. Each ranker retrieves the top 100 for every judged topic; the runs execute in the background worker.")}
      />
    );
  }

  const groups: Array<{ edition: string; specs: MetricSpec[] }> = [];
  for (const spec of columns) {
    const last = groups[groups.length - 1];
    if (last && last.edition === spec.edition) last.specs.push(spec);
    else groups.push({ edition: spec.edition, specs: [spec] });
  }

  return (
    <div className="space-y-6">
      <Card
        title={t("Aggregate metrics (macro-averaged over topics)")}
        subtitle={
          <span>
            {t("num_q first — every mean is over that many topics. Best value per column in bold. † / ‡ mark a Holm–Bonferroni-corrected p < 0.05 / 0.01 against the baseline ({baseline}) on {metric}.", { baseline: rankerLabel(baseline?.ranker ?? "vector"), metric: ctx.search.metric })}
          </span>
        }
        padding="sm"
      >
        {details.some((d) => d.isError) && <ErrorState error={details.find((d) => d.isError)?.error} compact />}
        <TableFrame>
          <Table>
            <thead>
              <tr>
                <Th rowSpan={2}>{t("ranker")}</Th>
                <Th numeric rowSpan={2}>
                  num_q
                </Th>
                {groups.map((g) => (
                  <Th key={g.edition} colSpan={g.specs.length} className="text-center !text-text-tertiary">
                    {editionLabel(g.edition)}
                  </Th>
                ))}
                <Th numeric rowSpan={2}>
                  {t("unjudged")}
                </Th>
                <Th numeric rowSpan={2}>
                  top_k
                </Th>
              </tr>
              <tr>
                {columns.map((spec) => (
                  <Th key={spec.key} numeric>
                    <MetricHeader spec={spec} />
                    {footnote.has(spec.key) && <sup className="text-caution">{sup(footnote.get(spec.key) ?? 0)}</sup>}
                  </Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loaded
                .slice()
                .sort((a, b) => (b.aggregate.find((m) => m.metric_key === "ap")?.value ?? 0) - (a.aggregate.find((m) => m.metric_key === "ap")?.value ?? 0))
                .map((run) => {
                  const numQ = run.aggregate.find((a) => a.metric_key === "ap")?.query_count ?? run.scored_query_count;
                  return (
                    <tr key={run.id}>
                      <Td>
                        <span className="inline-flex items-center gap-2">
                          <span aria-hidden className="size-2.5 rounded-full" style={{ background: rankerColor(run.ranker) }} />
                          <span className="font-medium">{rankerLabel(run.ranker)}</span>
                          {run.ranker === baseline?.ranker && <Badge>{t("baseline")}</Badge>}
                          {daggers.get(run.id) && <span className="text-accent" title={t("significant vs baseline")}>{daggers.get(run.id)}</span>}
                        </span>
                      </Td>
                      <Td numeric>{numQ}</Td>
                      {columns.map((spec) => {
                        const cell = run.aggregate.find((a) => a.metric_key === spec.key);
                        if (footnote.has(spec.key)) {
                          return (
                            <Td key={spec.key} numeric className="text-text-tertiary">
                              {t("n/a")}<sup>{sup(footnote.get(spec.key) ?? 0)}</sup>
                            </Td>
                          );
                        }
                        const isBest = cell !== undefined && best.get(spec.key) === cell.value;
                        return (
                          <Td key={spec.key} numeric strong={isBest}>
                            {fmtMetric(cell?.value)}
                          </Td>
                        );
                      })}
                      <Td numeric>{fmtInt(run.unjudged_retrieved)}</Td>
                      <Td numeric>{run.top_k}</Td>
                    </tr>
                  );
                })}
            </tbody>
          </Table>
        </TableFrame>
        {(degenerate.length > 0 || notes.length > 0) && (
          <div className="mt-3 space-y-1 text-caption text-text-secondary">
            {degenerate.map((c, i) => (
              <p key={c.metric_key}>
                <sup className="text-caution">{sup(i + 1)}</sup> {translateCaveat(c.note)}
              </p>
            ))}
            {notes.map((c) => (
              <p key={`${c.metric_key}-${c.note.slice(0, 12)}`}>· {translateCaveat(c.note)}</p>
            ))}
          </div>
        )}
      </Card>

      <GroupedBarsWithCI
        metrics={["ap", "p_5", "p_10", "rprec", "ndcg_10"].filter((k) => !footnote.has(k) && specByKey.has(k))}
        labels={Object.fromEntries(specs.map((s) => [s.key, metricLabel(s)]))}
        runs={loaded.map((run) => ({
          ranker: run.ranker,
          values: Object.fromEntries(run.aggregate.map((a) => [a.metric_key, { value: a.value, ci_low: a.ci_low ?? null, ci_high: a.ci_high ?? null }])),
        }))}
      />
    </div>
  );
}
