import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { HelpTip } from "@/components/ui/HelpTip";
import { PageHeader } from "@/components/ui/PageHeader";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useEvaluationContext } from "@/features/evaluation/useEvaluationContext";
import { t } from "@/lib/i18n";

const TABS = [
  { to: "/evaluation", label: "Overview", exact: true },
  { to: "/evaluation/per-query", label: "Per topic" },
  { to: "/evaluation/curves", label: "Curves" },
  { to: "/evaluation/compare", label: "Comparison" },
  { to: "/evaluation/significance", label: "Significance" },
  { to: "/evaluation/collection", label: "Collection & pool" },
  { to: "/evaluation/judge", label: "Judge" },
] as const;

export function EvaluationLayout() {
  const ctx = useEvaluationContext();
  const queryClient = useQueryClient();

  const startRuns = useMutation({
    mutationFn: () =>
      api.eval.startRuns({
        collection_id: ctx.collection?.id ?? 0,
        aggregation: ctx.qrelSet?.aggregation ?? "or",
        threshold: ctx.qrelSet?.threshold ?? 1,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.eval.all }),
  });

  const materialise = useMutation({
    mutationFn: (aggregation: string) => api.eval.materializeQrels(ctx.collection?.id ?? 0, aggregation, 1),
    onSuccess: (set) => {
      void queryClient.invalidateQueries({ queryKey: keys.eval.all });
      ctx.setSearch({ qrelSet: set.id });
    },
  });

  const qrelOptions = ctx.qrelSets.map((q) => ({
    value: String(q.id),
    label: `${q.aggregation} · num_q=${q.query_count}`,
    hint: q.aggregation === "or" ? t("weak requirements (or): relevant if any assessor said so") : t("strong requirements (and): non-relevant if any assessor said so"),
  }));

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow={t("Quality evaluation")}
        title={t("Evaluation")}
        description={t("ROMIP 2004 metrics computed programmatically over stored runs, shown as tables and graphs. Every number is traceable to the run, the relevance table and the index version that produced it.")}
        helpAnchor="help-evaluation"
        actions={
          <Button
            variant="primary"
            loading={startRuns.isPending}
            disabled={!ctx.collection || !ctx.qrelSet || ctx.activeRuns.length > 0}
            onClick={() => startRuns.mutate()}
            title={t("Run every ranker over the judged topics of this collection")}
          >
            {ctx.activeRuns.length > 0 ? t("Running {n} run(s)…", { n: ctx.activeRuns.length }) : t("Run all rankers")}
          </Button>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-card border border-hairline bg-surface p-4 shadow-sm">
        <label className="flex items-center gap-2 text-caption text-text-secondary">
          {t("Collection")}
          <select
            value={ctx.collection?.id ?? ""}
            onChange={(event) => ctx.setSearch({ collection: Number(event.target.value), qrelSet: undefined, run: undefined })}
            className="rounded-pill border border-hairline bg-surface px-3 py-1.5 text-[14px] text-text"
            aria-label={t("Test collection")}
          >
            {ctx.collections.map((c) => (
              <option key={c.id} value={c.id}>
                {t(c.name)} — {t("{n} judged topics", { n: c.summary.judged_queries ?? 0 })}
              </option>
            ))}
          </select>
          <HelpTip anchor="help-collections">
            {t("The known-item collection is built automatically (one relevant document per topic). The topical collection is hand-authored and judged over a pool by an LLM assessor — the stronger evidence.")}
          </HelpTip>
        </label>

        <div className="flex items-center gap-2 text-caption text-text-secondary">
          {t("Relevance table")}
          {qrelOptions.length > 0 ? (
            <SegmentedControl
              ariaLabel={t("Relevance table (assessor aggregation)")}
              size="sm"
              options={qrelOptions}
              value={String(ctx.qrelSet?.id ?? "")}
              onChange={(value) => ctx.setSearch({ qrelSet: Number(value), run: undefined })}
            />
          ) : (
            <span className="text-text-tertiary">{t("none yet")}</span>
          )}
          <Button size="sm" variant="ghost" loading={materialise.isPending} onClick={() => materialise.mutate("or")} disabled={!ctx.collection}>
            {t("build «or»")}
          </Button>
          <Button size="sm" variant="ghost" loading={materialise.isPending} onClick={() => materialise.mutate("and")} disabled={!ctx.collection}>
            {t("build «and»")}
          </Button>
          <HelpTip anchor="glossary-qrels">
            {t("ROMIP scores binary relevance derived from graded judgments at threshold relevant−, under two aggregations. Topics with no relevant document are excluded, so num_q is shown with every table.")}
          </HelpTip>
        </div>

        {ctx.qrelSet && (
          <span className="ml-auto flex flex-wrap items-center gap-2 text-caption">
            <Badge>{t("threshold ≥ {n}", { n: ctx.qrelSet.threshold })}</Badge>
            <Badge>{t("{n} relevant pairs", { n: ctx.qrelSet.relevant_count })}</Badge>
            <Badge>{t("{n} judged", { n: ctx.qrelSet.judged_count })}</Badge>
            {ctx.latestRuns.length > 0 && <Badge tone="accent">{t("{n} finished rankers", { n: ctx.latestRuns.length })}</Badge>}
          </span>
        )}
      </div>

      {startRuns.isError && <ErrorState error={startRuns.error} compact />}
      {materialise.isError && <ErrorState error={materialise.error} compact />}

      <nav aria-label={t("Evaluation sections")} className="mb-6 -mx-1 overflow-x-auto">
        <ul className="flex gap-1 whitespace-nowrap px-1 hairline-b">
          {TABS.map((tab) => (
            <li key={tab.to}>
              <Link
                to={tab.to}
                search={(prev) => prev}
                activeOptions={{ exact: "exact" in tab && tab.exact }}
                className="inline-block border-b-2 border-transparent px-3 py-2 text-[15px] text-text-secondary hover:text-text"
                activeProps={{ className: "!border-accent !text-accent font-medium", "aria-current": "page" }}
              >
                {t(tab.label)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <Outlet />
    </div>
  );
}
