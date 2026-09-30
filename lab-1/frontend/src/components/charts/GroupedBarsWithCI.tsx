import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { rankerColor, rankerLabel } from "./rankerColor";
import { AXIS, GRID, TOOLTIP_STYLE, UNIT_DOMAIN, fmt3 } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

export interface RunValues {
  ranker: string;
  label?: string;
  values: Record<string, { value: number; ci_low?: number | null; ci_high?: number | null }>;
}

/** Metric × ranker grouped bars with bootstrap confidence intervals as error bars. */
export function GroupedBarsWithCI({ metrics, runs, labels }: { metrics: string[]; runs: RunValues[]; labels: Record<string, string> }) {
  const data = metrics.map((metric) => {
    const row: Record<string, number | string | [number, number]> = { metric: labels[metric] ?? metric };
    for (const run of runs) {
      const entry = run.values[metric];
      if (!entry) continue;
      row[run.ranker] = entry.value;
      if (entry.ci_low != null && entry.ci_high != null) {
        row[`${run.ranker}__ci`] = [Math.max(0, entry.value - entry.ci_low), Math.max(0, entry.ci_high - entry.value)];
      }
    }
    return row;
  });
  return (
    <ChartFrame
      title={t("Rankers by metric, with 95% bootstrap intervals")}
      ariaLabel={t("Grouped bars of each ranker's mean per metric with confidence intervals")}
      height={320}
      caption={t("Error bars are percentile bootstrap intervals over topics (10 000 resamples). Overlapping intervals do not by themselves mean no difference — see the significance tab.")}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }} barCategoryGap="20%">
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey="metric" {...AXIS} />
          <YAxis domain={UNIT_DOMAIN} {...AXIS} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(value: number, name: string) => [fmt3(value), rankerLabel(name)]} />
          <Legend formatter={(value: string) => rankerLabel(value)} wrapperStyle={{ fontSize: 12 }} />
          {runs.map((run) => (
            <Bar key={run.ranker} dataKey={run.ranker} name={run.ranker} fill={rankerColor(run.ranker)} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              <ErrorBar dataKey={`${run.ranker}__ci`} width={4} strokeWidth={1.5} stroke="var(--text-secondary)" direction="y" />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
