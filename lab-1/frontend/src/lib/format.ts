/** Shared formatters. Kept in one place so tables and charts agree on precision. */

export const fmtScore = (value: number, digits = 4): string =>
  Number.isFinite(value) ? value.toFixed(digits) : "—";

export const fmtMetric = (value: number | null | undefined, digits = 4): string =>
  value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : value.toFixed(digits);

export const fmtMs = (ms: number): string =>
  ms < 1 ? `${(ms * 1000).toFixed(0)} µs` : ms < 1000 ? `${ms.toFixed(1)} ms` : `${(ms / 1000).toFixed(2)} s`;

export const fmtInt = (value: number): string => value.toLocaleString("en-US");

export const fmtBytes = (bytes: number): string => {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
};

export const fmtTime = (ts: string | number): string => {
  const date = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleTimeString("en-GB", { hour12: false }) +
        "." +
        String(date.getMilliseconds()).padStart(3, "0");
};

export const cx = (...parts: Array<string | false | null | undefined>): string =>
  parts.filter(Boolean).join(" ");

/** ISO date or datetime → `3 Sep 2026`. */
export const fmtDate = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
};

/** ISO datetime → `3 Sep 2026, 09:27`. */
export const fmtDateTime = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const fmtPct = (value: number | null | undefined, digits = 0): string =>
  value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${(value * 100).toFixed(digits)}%`;

/** Signed difference, e.g. `+0.1805`. */
export const fmtDelta = (value: number | null | undefined, digits = 4): string =>
  value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;

export const fmtP = (value: number | null | undefined): string =>
  value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : value < 0.0001
      ? "<0.0001"
      : value.toFixed(4);
