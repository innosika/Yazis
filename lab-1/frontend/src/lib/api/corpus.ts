import { z } from "zod";
import { del, get, post, query } from "./client";

export const collectionStatsSchema = z
  .object({
    document_count: z.number(),
    term_count: z.number(),
    posting_count: z.number(),
    average_document_length: z.number(),
    index_version: z.number(),
    log_base: z.string(),
    built_at: z.string().nullish(),
    build_duration_ms: z.number().nullish(),
    embedded_document_count: z.number().default(0),
    is_stale: z.boolean().default(false),
  })
  .passthrough();
export type CollectionStats = z.infer<typeof collectionStatsSchema>;

export const documentSummarySchema = z
  .object({
    id: z.number(),
    url: z.string(),
    title: z.string(),
    source_domain: z.string(),
    published_at: z.string().nullish(),
    fetched_at: z.string().nullish(),
    language: z.string().nullish(),
    token_count: z.number().default(0),
    distinct_term_count: z.number().default(0),
    vector_norm: z.number().default(0),
    has_embedding: z.boolean().default(false),
  })
  .passthrough();
export type DocumentSummary = z.infer<typeof documentSummarySchema>;

export const keywordSchema = z.object({
  lemma: z.string(),
  term_frequency: z.number(),
  document_frequency: z.number(),
  inverse_frequency: z.number(),
  weight_raw: z.number(),
  weight_norm: z.number(),
});
export type Keyword = z.infer<typeof keywordSchema>;

export const documentDetailSchema = documentSummarySchema.extend({
  text: z.string(),
  description: z.string().nullish(),
  author: z.string().nullish(),
  http_status: z.number().nullish(),
  byte_size: z.number().nullish(),
  keywords: z.array(keywordSchema).default([]),
});
export type DocumentDetail = z.infer<typeof documentDetailSchema>;

export const addDocumentSchema = z
  .object({ crawl_job_id: z.number(), url: z.string(), status: z.string(), message: z.string() })
  .passthrough();

export interface DocumentListParams {
  limit?: number;
  offset?: number;
  domain?: string;
  search?: string;
}

export const corpusApi = {
  stats: () => get("/corpus/stats", collectionStatsSchema),
  documents: (params: DocumentListParams) =>
    get(`/corpus/documents${query(params)}`, z.array(documentSummarySchema)),
  document: (id: number) => get(`/corpus/documents/${id}`, documentDetailSchema),
  remove: (id: number, reindex = true) =>
    del(`/corpus/documents/${id}${query({ reindex })}`, z.record(z.unknown())),
  rebuildIndex: (weightsOnly = false) =>
    post(`/corpus/index${query({ weights_only: weightsOnly })}`, z.record(z.unknown())),
  add: (url: string) => post("/corpus/documents", addDocumentSchema, { url }),
};
