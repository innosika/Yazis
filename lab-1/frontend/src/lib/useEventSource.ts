/**
 * Server-sent events as React state, validated with Zod.
 *
 * Pass the schema as a module-level constant and memoise the URL: both are effect
 * dependencies, and a fresh object per render would reconnect on every render.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { z } from "zod";

export type StreamState = "connecting" | "open" | "closed" | "error";

interface Options<T> {
  eventName?: string;
  limit?: number;
  enabled?: boolean;
  onRecord?: (record: T) => void;
  /** Consecutive browser-level errors tolerated before the stream gives up. */
  maxErrors?: number;
}

export interface EventSourceHandle<T> {
  records: T[];
  state: StreamState;
  clear: () => void;
  reconnect: () => void;
}

export function useEventSource<T>(
  url: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  { eventName = "message", limit = 500, enabled = true, onRecord, maxErrors = 5 }: Options<T> = {},
): EventSourceHandle<T> {
  const [records, setRecords] = useState<T[]>([]);
  const [state, setState] = useState<StreamState>("connecting");
  const [generation, setGeneration] = useState(0);
  const onRecordRef = useRef(onRecord);
  onRecordRef.current = onRecord;

  useEffect(() => {
    if (!enabled) {
      setState("closed");
      return;
    }
    setState("connecting");
    let errors = 0;
    const source = new EventSource(url);

    source.onopen = () => {
      errors = 0;
      setState("open");
    };
    source.onerror = () => {
      errors += 1;
      if (source.readyState === EventSource.CLOSED || errors >= maxErrors) {
        source.close();
        setState(source.readyState === EventSource.CLOSED && errors < maxErrors ? "closed" : "error");
        return;
      }
      setState("error");
    };

    const handler = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      const parsed = schema.safeParse(payload);
      if (!parsed.success) return;
      onRecordRef.current?.(parsed.data);
      setRecords((current) => {
        const next = [...current, parsed.data];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    };
    source.addEventListener(eventName, handler);

    return () => {
      source.removeEventListener(eventName, handler);
      source.close();
    };
  }, [url, eventName, limit, enabled, schema, maxErrors, generation]);

  const clear = useCallback(() => setRecords([]), []);
  const reconnect = useCallback(() => setGeneration((g) => g + 1), []);

  return { records, state, clear, reconnect };
}
