import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { rankerColor, rankerDash, rankerLabel } from "./rankerColor";
import { AXIS, GRID, TOOLTIP_STYLE, UNIT_DOMAIN, fmt3 } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import type { CurveSeries } from "./ElevenPointCurve";
import { t } from "@/lib/i18n";

export function PAtKChart({ series }: { series: CurveSeries[] }) {
  const rows = new Map<number, Record<string, number>>();
  for (const s of series) {
    for (const [k, value] of s.points) {
      if (k === undefined || value === undefined) continue;
      const row = rows.get(k) ?? { k };
      row[s.ranker] = value;
      rows.set(k, row);
    }
  }
  const data = [...rows.values()].sort((a, b) => (a.k ?? 0) - (b.k ?? 0));
  return (
    <ChartFrame
      title={t("Precision at k")}
      ariaLabel={t("Precision at cutoff k for each ranker")}
      caption={t("P@k divides by k even when fewer than k documents were returned. The official ROMIP cutoffs 5 and 10 are marked.")}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="k" type="number" domain={["dataMin", "dataMax"]} {...AXIS} />
          <YAxis domain={UNIT_DOMAIN} {...AXIS} />
          <ReferenceLine x={5} stroke="var(--hairline-strong)" strokeDasharray="2 2" />
          <ReferenceLine x={10} stroke="var(--hairline-strong)" strokeDasharray="2 2" />
          <Tooltip {...TOOLTIP_STYLE} formatter={(value: number, name: string) => [fmt3(value), rankerLabel(name)]} labelFormatter={(label: number) => `k = ${label}`} />
          <Legend formatter={(value: string) => rankerLabel(value)} wrapperStyle={{ fontSize: 12 }} />
          {series.map((s) => (
            <Line key={s.ranker} type="monotone" dataKey={s.ranker} name={s.ranker} stroke={rankerColor(s.ranker)} strokeWidth={2} strokeDasharray={rankerDash(s.ranker)} dot={{ r: 3, strokeWidth: 0, fill: rankerColor(s.ranker) }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
