import { z } from "zod";
import { get, post, query } from "./client";

export const spacePointSchema = z
  .object({
    document_id: z.number(),
    title: z.string(),
    url: z.string(),
    x: z.number(),
    y: z.number(),
    z: z.number(),
    cosine: z.number().default(0),
    rank: z.number().nullish(),
  })
  .passthrough();
export type SpacePoint = z.infer<typeof spacePointSchema>;

export const spaceSchema = z
  .object({
    index_version: z.number(),
    components: z.number(),
    explained_variance_ratio: z.number(),
    singular_values: z.array(z.number()).default([]),
    document_count: z.number(),
    points: z.array(spacePointSchema).default([]),
    query: z
      .object({
        text: z.string(),
        x: z.number(),
        y: z.number(),
        z: z.number(),
        lemmas: z.array(z.string()).default([]),
        unknown_lemmas: z.array(z.string()).default([]),
        terms_in_basis: z.number().default(0),
      })
      .nullish(),
    built_at: z.string().nullish(),
  })
  .passthrough();
export type Space = z.infer<typeof spaceSchema>;

export const queryTermSchema = z.object({
  term_id: z.number(),
  lemma: z.string(),
  weight: z.number(),
  previous_weight: z.number().nullish(),
  is_original: z.boolean().default(false),
});
export type QueryTerm = z.infer<typeof queryTermSchema>;

export const rankingEntrySchema = z
  .object({
    rank: z.number(),
    document_id: z.number(),
    title: z.string(),
    url: z.string(),
    score: z.number(),
    matched_lemmas: z.array(z.string()).default([]),
    previous_rank: z.number().nullish(),
  })
  .passthrough();
export type RankingEntry = z.infer<typeof rankingEntrySchema>;

export const iterationSchema = z
  .object({
    iteration: z.number(),
    relevant: z.array(z.number()).default([]),
    non_relevant: z.array(z.number()).default([]),
    projection: z.array(z.number()).default([]),
    top: z.array(z.number()).default([]),
    term_count: z.number().default(0),
    alpha: z.number(),
    beta: z.number(),
    gamma: z.number(),
  })
  .passthrough();
export type Iteration = z.infer<typeof iterationSchema>;

export const feedbackSchema = z
  .object({
    session_id: z.number(),
    iteration: z.number(),
    original_query: z.string(),
    coefficients: z.record(z.number()),
    query_point: z.array(z.number()),
    query_terms: z.array(queryTermSchema).default([]),
    added_terms: z.array(queryTermSchema).default([]),
    dropped_terms: z.array(z.string()).default([]),
    ranking: z.array(rankingEntrySchema).default([]),
    total_candidates: z.number().default(0),
    history: z.array(iterationSchema).default([]),
    index_version: z.number(),
  })
  .passthrough();
export type Feedback = z.infer<typeof feedbackSchema>;

export interface FeedbackRequest {
  session_id?: number;
  query: string;
  relevant: number[];
  non_relevant: number[];
  alpha?: number;
  beta?: number;
  gamma?: number;
  limit?: number;
}

export const labApi = {
  space: (queryText?: string) => get(`/lab/space${query({ query: queryText })}`, spaceSchema),
  rebuild: (components?: number) =>
    post("/lab/space/build", z.record(z.unknown()), { components: components ?? null }),
  feedback: (body: FeedbackRequest) => post("/lab/feedback", feedbackSchema, body),
  history: (sessionId: number) => get(`/lab/feedback/${sessionId}`, z.array(iterationSchema)),
};
