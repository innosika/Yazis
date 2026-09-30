/**
 * Live log console.
 *
 * The assignment requires comprehensible logging; this makes it visible in the product
 * rather than only in `docker logs`. Records arrive over SSE from a Redis channel that
 * both the API and the crawl worker publish to, so one console shows the whole system.
 */
import { useMemo, useRef, useState, useEffect } from "react";
import { logRecordSchema, type LogRecord } from "@/lib/api";
import { useEventSource } from "@/lib/useEventSource";
import { cx, fmtTime } from "@/lib/format";
import { t } from "@/lib/i18n";

const LEVELS = ["debug", "info", "warning", "error"] as const;
type Level = (typeof LEVELS)[number];

const LEVEL_STYLE: Record<string, string> = {
  debug: "text-text-tertiary",
  info: "text-accent",
  warning: "text-caution",
  error: "text-negative",
  critical: "text-negative",
};

interface Props {
  loggerPrefix?: string;
  minLevel?: Level;
  height?: string;
  className?: string;
}

export function LogConsole({
  loggerPrefix,
  minLevel = "info",
  height = "20rem",
  className,
}: Props) {
  const [level, setLevel] = useState<Level>(minLevel);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const url = useMemo(() => {
    const params = new URLSearchParams({ min_level: level });
    if (loggerPrefix) params.set("logger_prefix", loggerPrefix);
    return `/api/stream/logs?${params.toString()}`;
  }, [level, loggerPrefix]);

  const { records, state, clear } = useEventSource<LogRecord>(url, logRecordSchema, {
    eventName: "log",
    limit: 1000,
    enabled: !paused,
  });

  // Follow the tail only while the user has not scrolled away from it.
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [records, autoScroll]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  };

  return (
    <div
      className={cx(
        "overflow-hidden rounded-card border border-hairline bg-surface-sunken",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-3 border-b border-hairline px-4 py-2.5">
        <span
          className="flex items-center gap-2 text-caption font-medium"
          aria-live="polite"
        >
          <span
            aria-hidden
            className={cx(
              "size-2 rounded-full",
              state === "open"
                ? "bg-positive"
                : state === "connecting"
                  ? "bg-caution"
                  : "bg-text-tertiary",
            )}
          />
          {state === "open" ? "Streaming" : state === "connecting" ? "Connecting" : "Paused"}
        </span>

        <label className="flex items-center gap-1.5 text-caption text-text-secondary">
          <span>Level</span>
          <select
            value={level}
            onChange={(event) => setLevel(event.target.value as Level)}
            className="rounded-md border border-hairline bg-surface px-2 py-1 text-caption"
          >
            {LEVELS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className="rounded-pill border border-hairline px-3 py-1 text-caption transition-colors hover:bg-surface"
          >
            {paused ? t("Resume") : t("Pause")}
          </button>
          <button
            type="button"
            onClick={clear}
            className="rounded-pill border border-hairline px-3 py-1 text-caption transition-colors hover:bg-surface"
          >
            {t("Clear")}
          </button>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        style={{ height }}
        className="overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed"
        role="log"
        aria-label={t("Application log")}
      >
        {records.length === 0 ? (
          <p className="text-text-tertiary">
            No records yet. Start a crawl or run a search to produce log output.
          </p>
        ) : (
          records.map((record, index) => (
            <div
              key={`${record.ts}-${index}`}
              className="flex gap-2 border-b border-hairline/40 py-1 last:border-0"
            >
              <span className="shrink-0 text-text-tertiary">{fmtTime(record.ts)}</span>
              <span
                className={cx(
                  "w-14 shrink-0 font-semibold uppercase",
                  LEVEL_STYLE[record.level] ?? "text-text-secondary",
                )}
              >
                {record.level}
              </span>
              <span className="shrink-0 text-text-tertiary">
                {record.logger.replace(/^irs\./, "")}
              </span>
              <span className="font-semibold">{record.event}</span>
              <span className="min-w-0 flex-1 break-words text-text-secondary">
                {Object.entries(record.fields)
                  .filter(([key]) => key !== "stack" && key !== "exception")
                  .map(([key, value]) => `${key}=${formatValue(value)}`)
                  .join(" ")}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "string") return value.length > 120 ? `${value.slice(0, 120)}…` : value;
  return JSON.stringify(value) ?? "";
}
