import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, TOOLTIP_STYLE } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

export interface DivergingRow {
  topic: string;
  ext_id: number;
  delta: number;
}

/** Per-topic difference against the baseline: which topics a ranker wins and loses. */
export function DivergingAPBars({ rows, metric, rankerLabel, baselineLabel }: { rows: DivergingRow[]; metric: string; rankerLabel: string; baselineLabel: string }) {
  const data = [...rows].sort((a, b) => a.delta - b.delta);
  const wins = data.filter((r) => r.delta > 1e-9).length;
  const losses = data.filter((r) => r.delta < -1e-9).length;
  return (
    <ChartFrame
      title={t("{ranker} − {baseline}, per topic ({metric})", { ranker: rankerLabel, baseline: baselineLabel, metric })}
      ariaLabel={t("Per-topic difference in {metric} between {ranker} and {baseline}", { ranker: rankerLabel, baseline: baselineLabel, metric })}
      height={Math.max(160, 18 * data.length + 40)}
      caption={t("{wins} topics improved, {losses} worsened, {ties} tied. Sorted by difference.", { wins, losses, ties: data.length - wins - losses })}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <XAxis type="number" domain={[-1, 1]} {...AXIS} tickFormatter={(v: number) => v.toFixed(1)} />
          <YAxis type="category" dataKey="ext_id" width={36} {...AXIS} />
          <ReferenceLine x={0} stroke="var(--hairline-strong)" />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(value: number, _n, item) => [`${value >= 0 ? "+" : ""}${value.toFixed(4)}`, (item.payload as DivergingRow).topic]}
            labelFormatter={(label: number) => `${t("topic")} ${label}`}
          />
          <Bar dataKey="delta" isAnimationActive={false} radius={3}>
            {data.map((row) => (
              <Cell key={row.ext_id} fill={row.delta >= 0 ? "var(--positive)" : "var(--negative)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
