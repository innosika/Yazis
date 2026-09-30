/**
 * The one ranker→colour mapping, sourced from `theme.css` (`--ranker-*`).
 *
 * Recharts accepts `var(--ranker-vector)` directly in SVG presentation attributes; Three.js
 * needs real hex values, which `resolveRankerColor` reads from the computed style.
 */
import { t } from "@/lib/i18n";
export const RANKER_KEYS = [
  "vector",
  "vector_idf",
  "vector_prf",
  "bm25",
  "fts",
  "semantic",
  "hybrid",
] as const;
export type KnownRanker = (typeof RANKER_KEYS)[number];

const cssName = (key: string): string => `--ranker-${key.replace(/_/g, "-")}`;

export const RANKER_COLOR: Record<KnownRanker, string> = Object.fromEntries(
  RANKER_KEYS.map((key) => [key, `var(${cssName(key)})`]),
) as Record<KnownRanker, string>;

/** Secondary encoding for the vector family, so the three blues also differ by stroke. */
export const RANKER_DASH: Partial<Record<KnownRanker, string>> = {
  vector_idf: "6 3",
  vector_prf: "2 3",
};

export const RANKER_LABEL: Record<KnownRanker, string> = {
  vector: "Vector",
  vector_idf: "Vector · IDF query",
  vector_prf: "Vector · Rocchio PRF",
  bm25: "BM25",
  fts: "PostgreSQL FTS",
  semantic: "Semantic",
  hybrid: "Hybrid",
};

export const isKnownRanker = (key: string): key is KnownRanker =>
  (RANKER_KEYS as readonly string[]).includes(key);

export function rankerColor(key: string): string {
  return isKnownRanker(key) ? RANKER_COLOR[key] : "var(--text-tertiary)";
}

export function rankerLabel(key: string): string {
  return isKnownRanker(key) ? t(RANKER_LABEL[key]) : key;
}

export function rankerDash(key: string): string | undefined {
  return isKnownRanker(key) ? RANKER_DASH[key] : undefined;
}

/** Concrete colour for canvases that cannot read CSS variables (Three.js). */
export function resolveCssVar(name: string, fallback = "#888888"): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Order rankers for display: the mandated model first, then its variants, then the rest. */
export function rankerOrder(a: string, b: string): number {
  const index = (key: string) => {
    const i = (RANKER_KEYS as readonly string[]).indexOf(key);
    return i === -1 ? RANKER_KEYS.length : i;
  };
  return index(a) - index(b) || a.localeCompare(b);
}
