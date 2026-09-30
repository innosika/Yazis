import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDelta, fmtMetric, fmtP } from "@/lib/format";
import { keys } from "@/lib/queries";
import { SignificanceHeatmap } from "@/components/charts/SignificanceHeatmap";
import { rankerLabel } from "@/components/charts/rankerColor";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Skeleton } from "@/components/ui/Skeleton";
import { Table, TableFrame, Td, Th } from "@/components/ui/Table";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";
import { metricLabel } from "@/lib/metricsRu";

const TESTS = [
  { value: "permutation", label: "Permutation", hint: "Sign-flip randomisation test — assumption-free, the default" },
  { value: "wilcoxon", label: "Wilcoxon", hint: "Signed-rank test, robust to skew" },
  { value: "ttest_rel", label: "Paired t", hint: "Reported because readers expect it; not to be leaned on at n < 20" },
] as const;

export function SignificancePage() {
  const ctx = useEvaluationContext();
  const runs = ctx.latestRuns;
  const ids = runs.map((r) => r.id);
  const metric = ctx.search.metric;
  const test = ctx.search.test;

  const results = useQuery({
    queryKey: keys.eval.significance(ids, metric, test),
    queryFn: () => api.eval.significance(ids, metric, test),
    enabled: ids.length >= 2,
  });
  const scalarMetrics = (ctx.metrics?.metrics ?? []).filter((m) => m.kind === "scalar" && m.edition !== "diagnostic");

  if (!ctx.collection) return <Skeleton lines={6} />;
  if (runs.length < 2) return <EmptyState title={t("Need at least two finished runs")} description={t("Run the rankers first.")} />;

  const n = results.data?.[0]?.sample_size;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl ariaLabel={t("Statistical test")} size="sm" options={TESTS.map((o) => ({ ...o, label: t(o.label), hint: t(o.hint) }))} value={test} onChange={(value) => ctx.setSearch({ test: value })} />
        <label className="flex items-center gap-2 text-caption text-text-secondary">
          {t("Metric")}
          <select value={metric} onChange={(event) => ctx.setSearch({ metric: event.target.value })} className="rounded-pill border border-hairline bg-surface px-2 py-1 text-caption text-text" aria-label={t("Metric to test")}>
            {scalarMetrics.map((m) => (
              <option key={m.key} value={m.key}>
                {metricLabel(m)}
              </option>
            ))}
          </select>
        </label>
        <HelpTip anchor="help-significance">
          {t("Tests run on paired per-topic vectors restricted to topics both runs scored. Holm–Bonferroni corrects across all pairs. With n ≈ 25–30 topics only medium-to-large effects (roughly 15–25% relative MAP) can reach significance; a small gap that is “not significant” is not evidence of equality.")}
        </HelpTip>
      </div>

      {results.isPending && <Skeleton lines={8} />}
      {results.isError && <ErrorState error={results.error} onRetry={() => void results.refetch()} />}
      {results.data && (
        <>
          <Card title={t("Pairwise {test} test on {metric}", { test: t(TESTS.find((o) => o.value === test)?.label ?? test), metric: (() => { const spec = ctx.metrics?.metrics.find((m) => m.key === metric); return spec ? metricLabel(spec) : metric; })() })} subtitle={n !== undefined ? t("n = {n} paired topics · Holm–Bonferroni across {pairs} pairs", { n, pairs: results.data.length }) : undefined}>
            <SignificanceHeatmap rankers={runs.map((r) => r.ranker)} results={results.data} />
          </Card>

          <Card title={t("All comparisons")} padding="sm">
            <TableFrame>
              <Table>
                <thead>
                  <tr>
                    <Th>{t("pair (A vs B)")}</Th>
                    <Th numeric>{t("mean A")}</Th>
                    <Th numeric>{t("mean B")}</Th>
                    <Th numeric>Δ (A − B)</Th>
                    <Th numeric>{t("95% CI of Δ")}</Th>
                    <Th numeric>p</Th>
                    <Th numeric>{t("p corrected")}</Th>
                    <Th numeric>d_z</Th>
                    <Th numeric>n</Th>
                    <Th numeric>{t("ties")}</Th>
                  </tr>
                </thead>
                <tbody>
                  {results.data.map((r) => {
                    const p = r.p_value_corrected ?? r.p_value;
                    return (
                      <tr key={`${r.label_a}-${r.label_b}`}>
                        <Td>
                          {rankerLabel(r.label_a.split("#")[0] ?? r.label_a)} {t("vs")} {rankerLabel(r.label_b.split("#")[0] ?? r.label_b)}
                          {p < 0.01 ? <span className="ml-1 text-accent">‡</span> : p < 0.05 ? <span className="ml-1 text-accent">†</span> : null}
                        </Td>
                        <Td numeric>{fmtMetric(r.mean_a)}</Td>
                        <Td numeric>{fmtMetric(r.mean_b)}</Td>
                        <Td numeric strong className={r.mean_difference > 0 ? "text-positive" : r.mean_difference < 0 ? "text-negative" : ""}>
                          {fmtDelta(r.mean_difference)}
                        </Td>
                        <Td numeric className="text-text-secondary">
                          {r.ci_low != null && r.ci_high != null ? `[${fmtDelta(r.ci_low, 3)}, ${fmtDelta(r.ci_high, 3)}]` : "—"}
                        </Td>
                        <Td numeric>{fmtP(r.p_value)}</Td>
                        <Td numeric strong={p < 0.05}>
                          {fmtP(p)}
                        </Td>
                        <Td numeric>{r.effect_size != null ? r.effect_size.toFixed(2) : "—"}</Td>
                        <Td numeric>{r.sample_size}</Td>
                        <Td numeric>{r.ties}</Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </TableFrame>
            <p className="mt-3 text-caption text-text-tertiary">
              {t("Δ is A − B on the paired topics; d_z = mean(Δ) / sd(Δ) is Cohen's effect size for paired data; the interval is a 10 000-sample percentile bootstrap. Ties are topics where both runs scored identically — common at small n and costly for power.")}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
