import { useMemo } from "react";
import { crawlProgressSchema, type CrawlProgress } from "@/lib/api";
import { useEventSource } from "@/lib/useEventSource";

const URL = "/api/crawl/stream";

/** Live crawl events, optionally filtered to one job. */
export function useCrawlProgress(jobId: number | undefined, enabled = true) {
  const stream = useEventSource<CrawlProgress>(URL, crawlProgressSchema, {
    eventName: "progress",
    limit: 400,
    enabled,
  });
  const records = useMemo(
    () => (jobId === undefined ? stream.records : stream.records.filter((r) => r.job_id === jobId)),
    [stream.records, jobId],
  );
  return { ...stream, records };
}
