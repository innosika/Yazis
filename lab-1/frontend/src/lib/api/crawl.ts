import { z } from "zod";
import { get, post, query } from "./client";

export const crawlJobSchema = z
  .object({
    id: z.number(),
    status: z.string(),
    seed_urls: z.array(z.string()).default([]),
    max_pages: z.number(),
    max_depth: z.number(),
    same_domain_only: z.boolean().default(true),
    respect_robots_txt: z.boolean().default(true),
    pages_fetched: z.number().default(0),
    pages_indexed: z.number().default(0),
    pages_skipped: z.number().default(0),
    pages_failed: z.number().default(0),
    urls_discovered: z.number().default(0),
    bytes_downloaded: z.number().default(0),
    skip_breakdown: z.record(z.number()).default({}),
    pending_urls: z.number().default(0),
    error: z.string().nullish(),
    started_at: z.string().nullish(),
    finished_at: z.string().nullish(),
    task_id: z.string().nullish(),
  })
  .passthrough();
export type CrawlJob = z.infer<typeof crawlJobSchema>;

export const crawlTaskSchema = z
  .object({
    id: z.number(),
    url: z.string(),
    depth: z.number(),
    status: z.string(),
    skip_reason: z.string().nullish(),
    http_status: z.number().nullish(),
    error: z.string().nullish(),
    document_id: z.number().nullish(),
    extracted_chars: z.number().nullish(),
    content_bytes: z.number().nullish(),
    stage_timings_ms: z.record(z.unknown()).nullish(),
  })
  .passthrough();
export type CrawlTask = z.infer<typeof crawlTaskSchema>;

/** One SSE `progress` event from the worker. Kept loose: fields vary by event. */
export const crawlProgressSchema = z
  .object({
    event: z.string(),
    job_id: z.number().optional(),
    url: z.string().optional(),
    title: z.string().nullish(),
    reason: z.string().nullish(),
    detail: z.string().nullish(),
    depth: z.number().optional(),
    chars: z.number().optional(),
    document_id: z.number().nullish(),
    fetched: z.number().optional(),
    indexed: z.number().optional(),
    skipped: z.number().optional(),
    failed: z.number().optional(),
    budget: z.number().optional(),
    duration_ms: z.number().optional(),
  })
  .passthrough();
export type CrawlProgress = z.infer<typeof crawlProgressSchema>;

export interface CrawlRequest {
  seed_urls: string[];
  max_pages: number;
  max_depth: number;
  same_domain_only: boolean;
}

export const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);

export const crawlApi = {
  start: (body: CrawlRequest) => post("/crawl/jobs", crawlJobSchema, body),
  jobs: (limit = 20) => get(`/crawl/jobs${query({ limit })}`, z.array(crawlJobSchema)),
  job: (id: number) => get(`/crawl/jobs/${id}`, crawlJobSchema),
  urls: (id: number, params: { status?: string; limit?: number; offset?: number }) =>
    get(`/crawl/jobs/${id}/urls${query(params)}`, z.array(crawlTaskSchema)),
};
