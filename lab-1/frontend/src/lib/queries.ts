/**
 * Query keys and shared query options for TanStack Query.
 *
 * Keys are hierarchical so `invalidateQueries({ queryKey: keys.corpus.all })` clears every
 * corpus view after a document is added or removed.
 */
import { keepPreviousData, queryOptions } from "@tanstack/react-query";
import { api } from "./api";
import type { SearchRequest } from "./api";

export const keys = {
  health: ["health"] as const,
  search: {
    all: ["search"] as const,
    rankers: ["search", "rankers"] as const,
    results: (body: SearchRequest) => ["search", "results", body] as const,
    explain: (id: number, q: string) => ["search", "explain", id, q] as const,
  },
  corpus: {
    all: ["corpus"] as const,
    stats: ["corpus", "stats"] as const,
    documents: (params: Record<string, unknown>) => ["corpus", "documents", params] as const,
    document: (id: number) => ["corpus", "document", id] as const,
  },
  crawl: {
    all: ["crawl"] as const,
    jobs: ["crawl", "jobs"] as const,
    job: (id: number) => ["crawl", "job", id] as const,
    urls: (id: number, params: Record<string, unknown>) => ["crawl", "urls", id, params] as const,
  },
  eval: {
    all: ["eval"] as const,
    metrics: ["eval", "metrics"] as const,
    collections: ["eval", "collections"] as const,
    collection: (id: number) => ["eval", "collection", id] as const,
    topics: (id: number) => ["eval", "topics", id] as const,
    pool: (id: number) => ["eval", "pool", id] as const,
    qrelSets: (id: number) => ["eval", "qrel-sets", id] as const,
    runs: (params: Record<string, unknown>) => ["eval", "runs", params] as const,
    run: (id: number) => ["eval", "run", id] as const,
    runQueries: (id: number) => ["eval", "run", id, "queries"] as const,
    drilldown: (runId: number, queryId: number) => ["eval", "run", runId, "query", queryId] as const,
    curves: (id: number) => ["eval", "run", id, "curves"] as const,
    compare: (ids: number[], metric: string) => ["eval", "compare", ids, metric] as const,
    significance: (ids: number[], metric: string, test: string) =>
      ["eval", "significance", ids, metric, test] as const,
    judgingJobs: (collectionId?: number) => ["eval", "judging", collectionId ?? "all"] as const,
    judgingJob: (id: number) => ["eval", "judging-job", id] as const,
    assessorStatus: ["eval", "assessor-status"] as const,
    judgments: (collectionId: number, params: Record<string, unknown>) =>
      ["eval", "judgments", collectionId, params] as const,
  },
  lab: {
    space: (q: string) => ["lab", "space", q] as const,
  },
};

export const rankersQuery = queryOptions({
  queryKey: keys.search.rankers,
  queryFn: api.search.rankers,
  staleTime: 5 * 60_000,
});

export const corpusStatsQuery = queryOptions({
  queryKey: keys.corpus.stats,
  queryFn: api.corpus.stats,
});

export const metricsQuery = queryOptions({
  queryKey: keys.eval.metrics,
  queryFn: api.eval.metrics,
  staleTime: Infinity,
});

export const collectionsQuery = queryOptions({
  queryKey: keys.eval.collections,
  queryFn: api.eval.collections,
});

export const searchQuery = (body: SearchRequest) =>
  queryOptions({
    queryKey: keys.search.results(body),
    queryFn: () => api.search.run(body),
    enabled: body.query.trim().length > 0,
    placeholderData: keepPreviousData,
  });

/** Poll while anything in the list is still active. */
export const pollWhileActive =
  <T extends { status: string }>(active: Set<string>, intervalMs = 2_000) =>
  (query: { state: { data?: T[] | T | undefined } }): number | false => {
    const data = query.state.data;
    if (!data) return intervalMs;
    const rows = Array.isArray(data) ? data : [data];
    return rows.some((row) => active.has(row.status)) ? intervalMs : false;
  };
