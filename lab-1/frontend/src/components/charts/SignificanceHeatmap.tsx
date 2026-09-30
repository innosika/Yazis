import type { Significance } from "@/lib/api";
import { fmtDelta, fmtP } from "@/lib/format";
import { rankerLabel } from "./rankerColor";
import { t } from "@/lib/i18n";

/**
 * Upper-triangular grid of pairwise tests. A CSS grid rather than a chart library: each
 * cell is a real element with a full accessible label.
 */
export function SignificanceHeatmap({ rankers, results, alpha = 0.05 }: { rankers: string[]; results: Significance[]; alpha?: number }) {
  const lookup = new Map<string, Significance>();
  for (const r of results) {
    lookup.set(`${r.label_a}|${r.label_b}`, r);
    lookup.set(`${r.label_b}|${r.label_a}`, r);
  }
  const bin = (p: number | null | undefined): string => {
    if (p == null) return "transparent";
    if (p < 0.01) return "var(--accent)";
    if (p < alpha) return "color-mix(in srgb, var(--accent) 55%, var(--surface))";
    if (p < 0.1) return "color-mix(in srgb, var(--accent) 25%, var(--surface))";
    return "var(--surface-sunken)";
  };
  const marker = (p: number | null | undefined): string => (p == null ? "" : p < 0.01 ? "‡" : p < alpha ? "†" : "");

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid gap-1" style={{ gridTemplateColumns: `auto repeat(${rankers.length}, minmax(6.5rem, 1fr))` }} role="table" aria-label={t("Pairwise significance")}>
        <div />
        {rankers.map((r) => (
          <div key={r} role="columnheader" className="truncate px-1 text-center text-caption text-text-secondary">
            {rankerLabel(r)}
          </div>
        ))}
        {rankers.map((a, i) => (
          <RowFragment key={a} a={a} i={i} rankers={rankers} lookup={lookup} bin={bin} marker={marker} />
        ))}
      </div>
      <p className="mt-2 text-caption text-text-tertiary">
        {t("Cell = mean difference (row − column) on the primary metric; colour by Holm–Bonferroni-corrected p. † p < {alpha}, ‡ p < 0.01.", { alpha })}
      </p>
    </div>
  );
}

function RowFragment({ a, i, rankers, lookup, bin, marker }: { a: string; i: number; rankers: string[]; lookup: Map<string, Significance>; bin: (p: number | null | undefined) => string; marker: (p: number | null | undefined) => string }) {
  return (
    <>
      <div role="rowheader" className="flex items-center pr-2 text-caption text-text-secondary">
        {rankerLabel(a)}
      </div>
      {rankers.map((b, j) => {
        if (j <= i) return <div key={b} aria-hidden className="rounded bg-surface-sunken/40" />;
        const pair = [...lookup.values()].find(
          (r) => (r.label_a.startsWith(a) && r.label_b.startsWith(b)) || (r.label_a.startsWith(b) && r.label_b.startsWith(a)),
        );
        if (!pair) return <div key={b} className="rounded border border-dashed border-hairline text-center text-caption text-text-tertiary">—</div>;
        const sign = pair.label_a.startsWith(a) ? 1 : -1;
        const delta = sign * pair.mean_difference;
        const p = pair.p_value_corrected ?? pair.p_value;
        const dark = p != null && p < 0.05;
        return (
          <div
            key={b}
            role="cell"
            tabIndex={0}
            title={`${rankerLabel(a)} ${t("vs")} ${rankerLabel(b)}: Δ=${fmtDelta(delta)}, p=${fmtP(pair.p_value)}, ${t("corrected p")}=${fmtP(p)}, d_z=${pair.effect_size?.toFixed(2) ?? "—"}, n=${pair.sample_size}, ${t("ties")}=${pair.ties}`}
            aria-label={`${rankerLabel(a)} − ${rankerLabel(b)}: Δ ${fmtDelta(delta)}, ${t("corrected p")} ${fmtP(p)}, n ${pair.sample_size}`}
            className={`rounded px-2 py-2 text-center text-caption ${dark ? "text-on-accent" : "text-text"}`}
            style={{ background: bin(p) }}
          >
            <span className="tabular font-medium">{fmtDelta(delta, 3)}</span>
            <span className="ml-0.5">{marker(p)}</span>
            <span className="block text-[10px] opacity-80">p={fmtP(p)}</span>
          </div>
        );
      })}
    </>
  );
}
