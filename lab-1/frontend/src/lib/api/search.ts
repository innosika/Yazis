import { z } from "zod";
import { get, post } from "./client";
import { rankerKeySchema } from "./common";

export const highlightSchema = z.object({ start: z.number(), end: z.number(), lemma: z.string() });

export const searchHitSchema = z
  .object({
    document_id: z.number(),
    title: z.string(),
    url: z.string(),
    snippet: z.string(),
    rank: z.number(),
    date: z.string().nullish(),
    matched_lemmas: z.array(z.string()).default([]),
    highlights: z.array(highlightSchema).default([]),
    source_domain: z.string().default(""),
    token_count: z.number().default(0),
    detail: z.record(z.number()).default({}),
    snippet_is_query_biased: z.boolean().default(false),
  })
  .passthrough();
export type SearchHit = z.infer<typeof searchHitSchema>;

export const searchResponseSchema = z
  .object({
    query: z.string(),
    ranker: rankerKeySchema,
    hits: z.array(searchHitSchema).default([]),
    total_candidates: z.number().default(0),
    query_lemmas: z.array(z.string()).default([]),
    unknown_lemmas: z.array(z.string()).default([]),
    filters_applied: z.boolean().default(false),
    duration_ms: z.number().default(0),
    stage_timings_ms: z.record(z.number()).default({}),
    document_count: z.number().default(0),
    term_count: z.number().default(0),
    index_version: z.number().default(0),
  })
  .passthrough();
export type SearchResponse = z.infer<typeof searchResponseSchema>;

export const rankerSchema = z
  .object({
    key: rankerKeySchema,
    label: z.string(),
    description: z.string(),
    is_required_model: z.boolean().default(false),
    available: z.boolean().default(true),
    unavailable_reason: z.string().nullish(),
  })
  .passthrough();
export type RankerInfo = z.infer<typeof rankerSchema>;

export const termWeightSchema = z
  .object({
    lemma: z.string(),
    term_frequency: z.number(),
    document_frequency: z.number(),
    document_count: z.number(),
    inverse_frequency: z.number(),
    weight_raw: z.number(),
    weight_norm: z.number(),
    in_query: z.boolean().default(false),
  })
  .passthrough();
export type TermWeight = z.infer<typeof termWeightSchema>;

export const scoreStepSchema = z.object({
  lemma: z.string(),
  document_weight: z.number(),
  query_weight: z.number(),
  product: z.number(),
  running_sum: z.number(),
  share: z.number(),
});
export type ScoreStep = z.infer<typeof scoreStepSchema>;

export const explanationSchema = z
  .object({
    document_id: z.number(),
    title: z.string(),
    url: z.string(),
    document_count: z.number(),
    term_count: z.number(),
    log_base: z.string(),
    query_terms: z.array(termWeightSchema).default([]),
    missing_terms: z.array(z.string()).default([]),
    unknown_terms: z.array(z.string()).default([]),
    steps: z.array(scoreStepSchema).default([]),
    scalar_product: z.number().default(0),
    document_norm: z.number().default(0),
    query_norm: z.number().default(0),
    score: z.number().default(0),
    normalization_denominator: z.number().default(0),
    stored_document_norm: z.number().default(0),
    consistent_with_index: z.boolean().default(true),
    document_keywords: z.array(z.tuple([z.string(), z.number()])).default([]),
    distinct_term_count: z.number().default(0),
    token_count: z.number().default(0),
  })
  .passthrough();
export type ScoreExplanation = z.infer<typeof explanationSchema>;

export interface SearchRequest {
  query: string;
  ranker: string;
  limit?: number;
  offset?: number;
  all_words_together?: boolean;
  date_from?: string;
  date_to?: string;
  source_domain?: string;
}

export const searchApi = {
  rankers: () => get("/search/rankers", z.array(rankerSchema)),
  run: (body: SearchRequest) => post("/search", searchResponseSchema, body),
  explain: (documentId: number, queryText: string) =>
    get(`/search/explain/${documentId}?query=${encodeURIComponent(queryText)}`, explanationSchema),
};
