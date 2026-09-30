import { useMemo } from "react";
import { evalProgressSchema, type EvalProgress } from "@/lib/api";
import { useEventSource } from "@/lib/useEventSource";

const URL = "/api/eval/stream";

/** Live judging and run progress from the worker. */
export function useEvalProgress(kind?: "judging" | "runs", enabled = true) {
  const stream = useEventSource<EvalProgress>(URL, evalProgressSchema, { eventName: "progress", limit: 300, enabled });
  const records = useMemo(() => (kind ? stream.records.filter((r) => r.kind === kind) : stream.records), [stream.records, kind]);
  return { ...stream, records };
}
