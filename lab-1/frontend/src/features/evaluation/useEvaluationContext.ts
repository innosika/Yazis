/**
 * Shared state of the Evaluation submenu: the chosen collection, relevance table and the
 * finished runs under it. Read from the URL, so every tab and deep link agrees.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { ACTIVE_RUN_STATUSES, api, type Collection, type QrelSet, type Run } from "@/lib/api";
import { collectionsQuery, keys, metricsQuery, pollWhileActive } from "@/lib/queries";
import { rankerOrder } from "@/components/charts/rankerColor";
import { evaluationRoute } from "@/routes/router";
import type { EvaluationSearch } from "@/routes/searchParams";

export function useEvaluationContext() {
  const search = evaluationRoute.useSearch();
  const navigate = useNavigate({ from: evaluationRoute.fullPath });

  const metrics = useQuery(metricsQuery);
  const collections = useQuery(collectionsQuery);

  const collection: Collection | undefined = useMemo(() => {
    const list = collections.data ?? [];
    if (search.collection) return list.find((c) => c.id === search.collection);
    // Prefer the human/LLM-judged topical collection when it has judgments.
    return (
      list.find((c) => !c.is_known_item && (c.summary.judgments ?? 0) > 0) ??
      list.find((c) => !c.is_known_item) ??
      list[0]
    );
  }, [collections.data, search.collection]);

  const qrelSets = useQuery({
    queryKey: keys.eval.qrelSets(collection?.id ?? 0),
    queryFn: () => api.eval.qrelSets(collection?.id ?? 0),
    enabled: collection !== undefined,
  });

  const qrelSet: QrelSet | undefined = useMemo(() => {
    const list = qrelSets.data ?? [];
    if (search.qrelSet) return list.find((q) => q.id === search.qrelSet);
    return list.find((q) => q.aggregation === "or" && q.threshold === 1) ?? list[0];
  }, [qrelSets.data, search.qrelSet]);

  const runsParams = {
    limit: 200,
    ...(collection ? { collection_id: collection.id } : {}),
    ...(qrelSet ? { qrel_set_id: qrelSet.id } : {}),
  };
  const runs = useQuery({
    queryKey: keys.eval.runs(runsParams),
    queryFn: () => api.eval.runs(runsParams),
    enabled: collection !== undefined && qrelSet !== undefined,
    refetchInterval: pollWhileActive<Run>(ACTIVE_RUN_STATUSES, 2_500),
  });

  /** Latest finished run per ranker under the selected relevance table. */
  const latestRuns: Run[] = useMemo(() => {
    const byRanker = new Map<string, Run>();
    for (const run of runs.data ?? []) {
      if (run.status !== "done") continue;
      const existing = byRanker.get(run.ranker);
      if (!existing || run.id > existing.id) byRanker.set(run.ranker, run);
    }
    return [...byRanker.values()].sort((a, b) => rankerOrder(a.ranker, b.ranker));
  }, [runs.data]);

  const activeRuns = (runs.data ?? []).filter((r) => ACTIVE_RUN_STATUSES.has(r.status));

  const baselineRun = latestRuns.find((r) => r.ranker === search.baseline) ?? latestRuns[0];
  const selectedRun = latestRuns.find((r) => r.id === search.run) ?? baselineRun;

  const setSearch = (patch: Partial<EvaluationSearch>) =>
    void navigate({ search: (prev) => ({ ...prev, ...patch }) });

  return {
    search,
    setSearch,
    metrics: metrics.data,
    metricsQuery: metrics,
    collections: collections.data ?? [],
    collectionsQuery: collections,
    collection,
    qrelSets: qrelSets.data ?? [],
    qrelSetsQuery: qrelSets,
    qrelSet,
    runsQuery: runs,
    latestRuns,
    activeRuns,
    baselineRun,
    selectedRun,
  };
}

export type EvaluationContext = ReturnType<typeof useEvaluationContext>;
