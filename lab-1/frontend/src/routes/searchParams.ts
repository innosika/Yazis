/**
 * URL search-parameter schemas. `.catch()` everywhere: a malformed URL degrades to the
 * default instead of throwing into the error boundary.
 */
import { z } from "zod";

export const searchSearchSchema = z.object({
  q: z.string().catch(""),
  ranker: z.string().catch("vector"),
  all: z.boolean().catch(false),
  from: z.string().optional().catch(undefined),
  to: z.string().optional().catch(undefined),
  limit: z.number().int().min(1).max(100).catch(10),
});
export type SearchSearch = z.infer<typeof searchSearchSchema>;

export const corpusSearchSchema = z.object({
  page: z.number().int().min(0).catch(0),
  domain: z.string().optional().catch(undefined),
  q: z.string().optional().catch(undefined),
});
export type CorpusSearch = z.infer<typeof corpusSearchSchema>;

export const crawlSearchSchema = z.object({
  job: z.number().int().positive().optional().catch(undefined),
  seed: z.string().optional().catch(undefined),
});
export type CrawlSearch = z.infer<typeof crawlSearchSchema>;

export const evaluationSearchSchema = z.object({
  collection: z.number().int().positive().optional().catch(undefined),
  qrelSet: z.number().int().positive().optional().catch(undefined),
  run: z.number().int().positive().optional().catch(undefined),
  runs: z.array(z.number().int().positive()).optional().catch(undefined),
  baseline: z.string().catch("vector"),
  metric: z.string().catch("ap"),
  test: z.string().catch("permutation"),
});
export type EvaluationSearch = z.infer<typeof evaluationSearchSchema>;

export const labSearchSchema = z.object({
  q: z.string().catch(""),
  session: z.number().int().positive().optional().catch(undefined),
});
export type LabSearch = z.infer<typeof labSearchSchema>;
