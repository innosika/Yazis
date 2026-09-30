import { z } from "zod";

/** Ranker keys stay open strings: new strategies arrive server-side first. */
export const rankerKeySchema = z.string().min(1);
export type RankerKey = z.infer<typeof rankerKeySchema>;

export const isoDateTime = z.string();
export const nullableNumber = z.number().nullish();

export const dependencyStatusSchema = z.object({
  name: z.string(),
  ok: z.boolean(),
  detail: z.string().nullish(),
  latency_ms: z.number().nullish(),
});

export const healthSchema = z
  .object({
    status: z.enum(["ok", "degraded"]),
    version: z.string(),
    environment: z.string(),
    dependencies: z.array(dependencyStatusSchema).default([]),
  })
  .passthrough();
export type Health = z.infer<typeof healthSchema>;

export const logRecordSchema = z
  .object({
    ts: z.union([z.string(), z.number()]),
    level: z.string(),
    logger: z.string(),
    event: z.string(),
    request_id: z.string().nullish(),
    fields: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type LogRecord = z.infer<typeof logRecordSchema>;

export const GRADES = [
  "VITAL",
  "RELEVANT_PLUS",
  "RELEVANT_MINUS",
  "NOTRELEVANT",
  "CANTBEJUDGED",
] as const;
export type Grade = (typeof GRADES)[number];
export const gradeSchema = z.string();
