import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Curve } from "@/lib/api";
import { keys } from "@/lib/queries";
import { ElevenPointCurve } from "@/components/charts/ElevenPointCurve";
import { GradeDistribution } from "@/components/charts/GradeDistribution";
import { PAtKChart } from "@/components/charts/PAtKChart";
import { PRCurve } from "@/components/charts/PRCurve";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Toggle } from "@/components/ui/Toggle";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";

export function CurvesPage() {
  const ctx = useEvaluationContext();
  const [overlayNonZeroing, setOverlay] = useState(false);
  const runs = ctx.latestRuns;

  const curves = useQueries({
    queries: runs.map((run) => ({ queryKey: keys.eval.curves(run.id), queryFn: () => api.eval.curves(run.id) })),
  });
  // The raw sawtooth is per topic; show the selected run's per-topic curves for its worst
  // and best topics would need drilldowns — instead the aggregate raw curve comes from the
  // per-query drilldown of the selected run's topics. Keep it simple: one topic sample.
  const queries = useQueries({
    queries: runs.map((run) => ({ queryKey: keys.eval.runQueries(run.id), queryFn: () => api.eval.runQueries(run.id) })),
  });

  if (!ctx.collection) return <Skeleton lines={6} />;
  if (runs.length === 0) return <EmptyState title={t("No finished runs")} description={t("Run the rankers first.")} />;
  if (curves.some((c) => c.isPending)) return <Skeleton lines={10} />;

  const byRun = new Map<number, Curve[]>();
  curves.forEach((c, i) => {
    const run = runs[i];
    if (run && c.data) byRun.set(run.id, c.data);
  });
  const pick = (key: string) =>
    runs.flatMap((run) => {
      const curve = byRun.get(run.id)?.find((c) => c.curve_key === key);
      return curve ? [{ ranker: run.ranker, points: curve.points, support: curve.support ?? null }] : [];
    });

  const trec = pick("iprec11");
  const nonZeroing = pick("iprec11_nz");
  const pAtK = pick("p_at_k");

  // Raw PR: the median-AP topic of the selected run, one sawtooth per ranker on that topic.
  const selected = ctx.selectedRun ?? runs[0];
  const selectedQueries = queries[runs.findIndex((r) => r.id === selected?.id)]?.data ?? [];
  const median = selectedQueries[Math.floor(selectedQueries.length / 2)];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-caption text-text-secondary">
          {t("Axes are pinned to [0, 1] so curves from different collections stay comparable. Colours follow the ranker legend used everywhere else.")}
        </p>
        <Toggle
          checked={overlayNonZeroing}
          onChange={setOverlay}
          label={t("Overlay the non-zeroing reconstruction")}
          description={t("Dashed: unreached recall levels are omitted instead of scored 0 — ROMIP's undefined 'RIRES' variant, reconstructed.")}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <ElevenPointCurve
          series={trec}
          caption={t("Precision interpolated at eleven recall levels and macro-averaged. A topic that never reaches a level contributes 0 to it — the TREC convention the appendix specifies.")}
        />
        {overlayNonZeroing ? (
          <ElevenPointCurve
            series={nonZeroing}
            ghost
            title={t("11-point curve, non-zeroing variant (reconstruction)")}
            caption={t("Averaged only over the topics that reached each level; n per level appears in the tooltip. Higher by construction at high recall — which is exactly what the zeroing rule guards against.")}
          />
        ) : (
          <PAtKChart series={pAtK} />
        )}
        {median && selected && (
          <RawCurves runs={runs} queryId={median.query_id} title={t("Raw PR on topic {id}: “{title}”", { id: median.ext_id, title: median.title })} />
        )}
        {overlayNonZeroing && <PAtKChart series={pAtK} />}
        <GradeDistribution counts={ctx.collection.grade_counts} title={t("Judgment grades in “{name}”", { name: t(ctx.collection.name) })} />
      </div>
    </div>
  );
}

function RawCurves({ runs, queryId, title }: { runs: Array<{ id: number; ranker: string }>; queryId: number; title: string }) {
  const drilldowns = useQueries({
    queries: runs.map((run) => ({
      queryKey: keys.eval.drilldown(run.id, queryId),
      queryFn: () => api.eval.drilldown(run.id, queryId, 100),
    })),
  });
  const series = runs.flatMap((run, i) => {
    const data = drilldowns[i]?.data;
    return data ? [{ ranker: run.ranker, points: data.pr_raw }] : [];
  });
  return (
    <PRCurve
      series={series}
      title={title}
      caption={t("One point per retrieved document: precision after each rank against recall so far. The interpolation on the left takes the running maximum from the right of this sawtooth.")}
    />
  );
}
