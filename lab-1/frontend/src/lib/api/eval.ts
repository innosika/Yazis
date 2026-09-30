import { z } from "zod";
import { get, getText, post, query } from "./client";
import { gradeSchema, rankerKeySchema } from "./common";

export const metricSpecSchema = z
  .object({
    key: z.string(),
    label: z.string(),
    description: z.string(),
    kind: z.string(),
    edition: z.string(),
    needs_graded: z.boolean().default(false),
    cutoff: z.number().nullish(),
    higher_is_better: z.boolean().default(true),
    formula_tex: z.string().nullish(),
    label_ru: z.string().nullish(),
  })
  .passthrough();
export type MetricSpec = z.infer<typeof metricSpecSchema>;

export const metricRegistrySchema = z
  .object({
    metrics: z.array(metricSpecSchema),
    primary_order: z.array(z.string()).default([]),
    curve_keys: z.array(z.string()).default([]),
    primary_metric: z.string().default("ap"),
  })
  .passthrough();
export type MetricRegistry = z.infer<typeof metricRegistrySchema>;

export const assessorSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    kind: z.string(),
    meta: z.record(z.unknown()).default({}),
    judgment_count: z.number().default(0),
  })
  .passthrough();
export type Assessor = z.infer<typeof assessorSchema>;

export const collectionSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    description: z.string().nullish(),
    frozen_at: z.string().nullish(),
    created_at: z.string().nullish(),
    summary: z.record(z.number()).default({}),
    topics_by_category: z.record(z.record(z.number())).default({}),
    grade_counts: z.record(z.number()).default({}),
    assessors: z.array(assessorSchema).default([]),
    pool_depth: z.number().default(10),
    is_known_item: z.boolean().default(false),
  })
  .passthrough();
export type Collection = z.infer<typeof collectionSchema>;

export const topicSchema = z
  .object({
    id: z.number(),
    ext_id: z.number(),
    title: z.string(),
    description: z.string().nullish(),
    narrative: z.string().nullish(),
    category: z.string().nullish(),
    is_judged: z.boolean(),
    selected_at: z.string().nullish(),
    oracle_query: z.string().nullish(),
    pool_size: z.number().default(0),
    judged_pairs: z.number().default(0),
  })
  .passthrough();
export type Topic = z.infer<typeof topicSchema>;

export const poolBuildSchema = z
  .object({
    topics: z.number(),
    entries: z.number(),
    by_source: z.record(z.number()).default({}),
    rankers: z.array(z.string()).default([]),
    oracle_ranker: z.string(),
    depth: z.number(),
    random_size: z.number(),
    duration_ms: z.number(),
  })
  .passthrough();

export const poolTopicSchema = z
  .object({
    query_id: z.number(),
    ext_id: z.number(),
    title: z.string(),
    category: z.string().nullish(),
    is_judged: z.boolean().default(false),
    total: z.number().default(0),
    judged: z.number().default(0),
    relevant: z.number().default(0),
    by_source: z.record(z.number()).default({}),
    by_ranker: z.record(z.number()).default({}),
  })
  .passthrough();
export type PoolTopic = z.infer<typeof poolTopicSchema>;

export const poolStatsSchema = z
  .object({
    depth: z.number(),
    unique_documents: z.number(),
    total_entries: z.number(),
    by_source: z.record(z.record(z.number())).default({}),
    per_topic: z.array(poolTopicSchema).default([]),
  })
  .passthrough();
export type PoolStats = z.infer<typeof poolStatsSchema>;

export const poolNextSchema = z
  .object({
    topic: z.object({
      id: z.number(),
      ext_id: z.number(),
      title: z.string(),
      description: z.string().nullish(),
      narrative: z.string().nullish(),
    }),
    document: z.object({ id: z.number(), title: z.string(), url: z.string(), text: z.string() }),
    remaining: z.number(),
    total: z.number(),
    judged_by_you: z.number().default(0),
    grades: z.array(z.string()).default([]),
  })
  .passthrough();
export type PoolNext = z.infer<typeof poolNextSchema>;

export const judgmentSchema = z
  .object({
    id: z.number(),
    query_id: z.number(),
    document_id: z.number(),
    assessor_id: z.number(),
    assessor: z.string(),
    grade: gradeSchema,
    seconds_spent: z.number().nullish(),
    note: z.string().nullish(),
    created_at: z.string().nullish(),
  })
  .passthrough();
export type Judgment = z.infer<typeof judgmentSchema>;

export const judgingJobSchema = z
  .object({
    id: z.number(),
    collection_id: z.number(),
    assessor_id: z.number(),
    assessor: z.string().nullish(),
    status: z.string(),
    task_id: z.string().nullish(),
    total_pairs: z.number(),
    judged_pairs: z.number(),
    failed_pairs: z.number(),
    pending_pairs: z.number().default(0),
    error: z.string().nullish(),
    started_at: z.string().nullish(),
    finished_at: z.string().nullish(),
    created_at: z.string().nullish(),
    model: z.string().nullish(),
  })
  .passthrough();
export type JudgingJob = z.infer<typeof judgingJobSchema>;

export const assessorStatusSchema = z
  .object({
    name: z.string(),
    meta: z.record(z.unknown()).default({}),
    reachable: z.boolean(),
    problem: z.string().nullish(),
  })
  .passthrough();

export const qrelSetSchema = z
  .object({
    id: z.number(),
    collection_id: z.number(),
    name: z.string(),
    aggregation: z.string(),
    threshold: z.number(),
    query_count: z.number(),
    relevant_count: z.number(),
    judged_count: z.number(),
    excluded_queries: z.number().nullish(),
    disagreement_count: z.number().nullish(),
  })
  .passthrough();
export type QrelSet = z.infer<typeof qrelSetSchema>;

export const runSchema = z
  .object({
    id: z.number(),
    collection_id: z.number(),
    qrel_set_id: z.number(),
    ranker: rankerKeySchema,
    label: z.string().nullish(),
    top_k: z.number(),
    status: z.string(),
    index_version: z.number(),
    params_snapshot: z.record(z.unknown()).default({}),
    scored_query_count: z.number().default(0),
    unjudged_retrieved: z.number().default(0),
    duration_ms: z.number().nullish(),
    batch_id: z.string().nullish(),
    error: z.string().nullish(),
    started_at: z.string().nullish(),
    finished_at: z.string().nullish(),
    created_at: z.string().nullish(),
    aggregation: z.string().nullish(),
    threshold: z.number().nullish(),
  })
  .passthrough();
export type Run = z.infer<typeof runSchema>;

export const runBatchSchema = z
  .object({ batch_id: z.string(), qrel_set: qrelSetSchema, runs: z.array(runSchema) })
  .passthrough();

export const aggregateMetricSchema = z.object({
  metric_key: z.string(),
  value: z.number(),
  query_count: z.number(),
  ci_low: z.number().nullish(),
  ci_high: z.number().nullish(),
});
export const caveatSchema = z.object({ metric_key: z.string(), kind: z.string(), note: z.string() });
export type Caveat = z.infer<typeof caveatSchema>;

export const runDetailSchema = runSchema.extend({
  aggregate: z.array(aggregateMetricSchema).default([]),
  caveats: z.array(caveatSchema).default([]),
});
export type RunDetail = z.infer<typeof runDetailSchema>;

export const queryMetricsSchema = z
  .object({
    query_id: z.number(),
    ext_id: z.number(),
    title: z.string(),
    category: z.string().nullish(),
    metrics: z.record(z.number()).default({}),
  })
  .passthrough();
export type QueryMetrics = z.infer<typeof queryMetricsSchema>;

export const rankedDocumentSchema = z
  .object({
    rank: z.number(),
    document_id: z.number(),
    title: z.string(),
    url: z.string(),
    score: z.number(),
    grade: z.string().nullish(),
    gain: z.number().nullish(),
    is_relevant: z.boolean().nullish(),
    is_judged: z.boolean().default(false),
  })
  .passthrough();
export type RankedDocument = z.infer<typeof rankedDocumentSchema>;

export const drilldownSchema = z
  .object({
    query: queryMetricsSchema,
    top: z.array(rankedDocumentSchema).default([]),
    pr_raw: z.array(z.array(z.number())).default([]),
    relevant_total: z.number().default(0),
    relevant_documents: z.array(rankedDocumentSchema).default([]),
  })
  .passthrough();
export type Drilldown = z.infer<typeof drilldownSchema>;

export const curveSchema = z.object({
  curve_key: z.string(),
  points: z.array(z.array(z.number())),
  support: z.array(z.array(z.number())).nullish(),
});
export type Curve = z.infer<typeof curveSchema>;

export const compareRowSchema = z
  .object({
    run_id: z.number(),
    ranker: z.string(),
    label: z.string(),
    mean_on_intersection: z.number(),
    ci_low: z.number().nullish(),
    ci_high: z.number().nullish(),
    stored_mean: z.number().nullish(),
    stored_query_count: z.number().default(0),
    dropped_topics: z.number().default(0),
    delta_vs_baseline: z.number().nullish(),
  })
  .passthrough();
export const compareSchema = z
  .object({
    metric: z.string(),
    topic_count: z.number(),
    baseline_run_id: z.number(),
    rows: z.array(compareRowSchema).default([]),
    per_topic: z
      .array(
        z
          .object({
            query_id: z.number(),
            ext_id: z.number().nullish(),
            values: z.record(z.number()).default({}),
          })
          .passthrough(),
      )
      .default([]),
  })
  .passthrough();
export type Compare = z.infer<typeof compareSchema>;

export const significanceSchema = z
  .object({
    metric_key: z.string(),
    test: z.string(),
    label_a: z.string(),
    label_b: z.string(),
    run_a_id: z.number().nullish(),
    run_b_id: z.number().nullish(),
    sample_size: z.number(),
    mean_a: z.number(),
    mean_b: z.number(),
    mean_difference: z.number(),
    p_value: z.number(),
    p_value_corrected: z.number().nullish(),
    correction: z.string().nullish(),
    statistic: z.number().nullish(),
    effect_size: z.number().nullish(),
    ci_low: z.number().nullish(),
    ci_high: z.number().nullish(),
    ties: z.number().default(0),
  })
  .passthrough();
export type Significance = z.infer<typeof significanceSchema>;

/** One SSE event on /eval/stream: judging progress or run progress. */
export const evalProgressSchema = z
  .object({
    kind: z.string(),
    event: z.string(),
    job_id: z.number().optional(),
    run_id: z.number().optional(),
    batch_id: z.string().nullish(),
    ranker: z.string().optional(),
    judged: z.number().optional(),
    failed: z.number().optional(),
    total: z.number().optional(),
    done: z.number().optional(),
    query_id: z.number().optional(),
    document_id: z.number().optional(),
    grade: z.string().optional(),
    map: z.number().optional(),
    p_10: z.number().optional(),
    error: z.string().optional(),
  })
  .passthrough();
export type EvalProgress = z.infer<typeof evalProgressSchema>;

export const ACTIVE_RUN_STATUSES = new Set(["pending", "running"]);

export const evalApi = {
  metrics: () => get("/eval/metrics", metricRegistrySchema),
  collections: () => get("/eval/collections", z.array(collectionSchema)),
  collection: (id: number) => get(`/eval/collections/${id}`, collectionSchema),
  seedTopical: (replace = false) =>
    post("/eval/collections/topical/seed", collectionSchema, { replace }),
  buildKnownItem: (size = 30, replace = false) =>
    post(`/eval/collections/known-item${query({ size, replace })}`, collectionSchema),
  topics: (collectionId: number, judgedOnly = false) =>
    get(
      `/eval/collections/${collectionId}/topics${query({ judged_only: judgedOnly })}`,
      z.array(topicSchema),
    ),
  selectTopics: (collectionId: number, count?: number) =>
    post(`/eval/collections/${collectionId}/topics/select`, z.array(topicSchema), {
      count: count ?? null,
    }),
  buildPool: (collectionId: number, body: { depth?: number; random_size?: number; replace?: boolean }) =>
    post(`/eval/collections/${collectionId}/pool`, poolBuildSchema, body),
  poolStats: (collectionId: number) =>
    get(`/eval/collections/${collectionId}/pool/stats`, poolStatsSchema),
  poolNext: async (collectionId: number, assessor: string): Promise<PoolNext | null> => {
    const response = await fetch(
      `${import.meta.env.VITE_API_BASE ?? "/api"}/eval/collections/${collectionId}/pool/next${query({ assessor })}`,
    );
    if (response.status === 204) return null;
    const payload: unknown = await response.json();
    if (!response.ok) throw new Error(`pool/next failed: HTTP ${response.status}`);
    return poolNextSchema.parse(payload);
  },
  assessors: () => get("/eval/assessors", z.array(assessorSchema)),
  createAssessor: (name: string) => post("/eval/assessors", assessorSchema, { name }),
  judge: (body: {
    query_id: number;
    document_id: number;
    assessor: string;
    grade: string;
    seconds_spent?: number;
    note?: string;
  }) => post("/eval/judgments", judgmentSchema, body),
  judgments: (collectionId: number, params: { query_id?: number; assessor?: string; limit?: number }) =>
    get(`/eval/collections/${collectionId}/judgments${query(params)}`, z.array(judgmentSchema)),
  startJudging: (collectionId: number, limit?: number) =>
    post(`/eval/collections/${collectionId}/judging`, judgingJobSchema, {
      limit: limit ?? null,
    }),
  judgingJobs: (collectionId?: number) =>
    get(`/eval/judging/jobs${query({ collection_id: collectionId })}`, z.array(judgingJobSchema)),
  judgingJob: (id: number) => get(`/eval/judging/jobs/${id}`, judgingJobSchema),
  assessorStatus: () => get("/eval/judging/assessor", assessorStatusSchema),
  materializeQrels: (collectionId: number, aggregation: string, threshold = 1) =>
    post(`/eval/collections/${collectionId}/qrel-sets`, qrelSetSchema, { aggregation, threshold }),
  qrelSets: (collectionId: number) =>
    get(`/eval/collections/${collectionId}/qrel-sets`, z.array(qrelSetSchema)),
  startRuns: (body: {
    collection_id: number;
    aggregation: string;
    threshold?: number;
    rankers?: string[];
    top_k?: number;
  }) => post("/eval/runs", runBatchSchema, body),
  runs: (params: {
    collection_id?: number;
    qrel_set_id?: number;
    batch_id?: string;
    status?: string;
    limit?: number;
  }) => get(`/eval/runs${query(params)}`, z.array(runSchema)),
  run: (id: number) => get(`/eval/runs/${id}`, runDetailSchema),
  runQueries: (id: number) => get(`/eval/runs/${id}/queries`, z.array(queryMetricsSchema)),
  drilldown: (runId: number, queryId: number, top = 10) =>
    get(`/eval/runs/${runId}/queries/${queryId}${query({ top })}`, drilldownSchema),
  curves: (id: number) => get(`/eval/runs/${id}/curves`, z.array(curveSchema)),
  trecRun: (id: number) => getText(`/eval/runs/${id}/trec`),
  trecQrels: (id: number) => getText(`/eval/qrel-sets/${id}/trec`),
  compare: (runIds: number[], metric = "ap") =>
    get(`/eval/compare${query({ runs: runIds.join(","), metric })}`, compareSchema),
  significance: (runIds: number[], metric = "ap", test = "permutation") =>
    get(
      `/eval/significance${query({ runs: runIds.join(","), metric, test })}`,
      z.array(significanceSchema),
    ),
  storedSignificance: (runId: number) =>
    get(`/eval/runs/${runId}/significance`, z.array(significanceSchema)),
};
