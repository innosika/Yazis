import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { rankerColor, rankerDash, rankerLabel } from "./rankerColor";
import { AXIS, GRID, RECALL_TICKS, TOOLTIP_STYLE, UNIT_DOMAIN, fmt3 } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

export interface RawSeries {
  ranker: string;
  label?: string;
  /** [recall, precision] after each retrieved document. */
  points: number[][];
}

/** The un-interpolated sawtooth, one point per retrieved document. */
export function PRCurve({ series, title = t("Raw precision–recall (sawtooth)"), caption }: { series: RawSeries[]; title?: string; caption?: string }) {
  return (
    <ChartFrame title={title} ariaLabel={t("Raw precision against recall, one point per retrieved document")} caption={caption}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="recall" type="number" domain={UNIT_DOMAIN} ticks={RECALL_TICKS} allowDataOverflow {...AXIS} />
          <YAxis dataKey="precision" type="number" domain={UNIT_DOMAIN} allowDataOverflow {...AXIS} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(value: number) => fmt3(value)} labelFormatter={(label: number) => `${t("recall")} ${fmt3(label)}`} />
          <Legend formatter={(value: string) => rankerLabel(value)} wrapperStyle={{ fontSize: 12 }} />
          {series.map((s) => (
            <Line
              key={s.ranker}
              data={s.points.map(([recall, precision]) => ({ recall, precision }))}
              dataKey="precision"
              name={s.ranker}
              type="linear"
              stroke={rankerColor(s.ranker)}
              strokeWidth={1.75}
              strokeDasharray={rankerDash(s.ranker)}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
