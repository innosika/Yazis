import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { rankerColor, rankerDash, rankerLabel } from "./rankerColor";
import { AXIS, GRID, RECALL_TICKS, TOOLTIP_STYLE, UNIT_DOMAIN, fmt3 } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

export interface CurveSeries {
  ranker: string;
  label?: string;
  points: number[][];
  /** Topics contributing at each level (non-zeroing variant). */
  support?: number[][] | null;
}

interface Props {
  series: CurveSeries[];
  title?: string;
  caption?: string;
  /** Draw the series dashed and dimmer (used for the non-zeroing overlay). */
  ghost?: boolean;
}

/** Merge per-series [recall, precision] points into one row per recall level. */
function toRows(series: CurveSeries[]): Array<Record<string, number>> {
  const rows = new Map<number, Record<string, number>>();
  for (const s of series) {
    for (const [recall, precision] of s.points) {
      if (recall === undefined || precision === undefined) continue;
      const key = Math.round(recall * 100) / 100;
      const row = rows.get(key) ?? { recall: key };
      row[s.ranker] = precision;
      if (s.support) {
        const at = s.support.find(([level]) => level !== undefined && Math.abs(level - key) < 1e-9);
        if (at?.[1] !== undefined) row[`${s.ranker}__n`] = at[1];
      }
      rows.set(key, row);
    }
  }
  return [...rows.values()].sort((a, b) => (a.recall ?? 0) - (b.recall ?? 0));
}

export function ElevenPointCurve({ series, title = t("11-point interpolated precision–recall (TREC method)"), caption, ghost }: Props) {
  const rows = toRows(series);
  return (
    <ChartFrame
      title={title}
      ariaLabel={t("Interpolated precision at eleven recall levels, one line per ranker")}
      caption={caption}
      table={
        <table className="text-caption">
          <thead>
            <tr>
              <th className="pr-2 text-left">{t("recall")}</th>
              {series.map((s) => (
                <th key={s.ranker} className="pr-2 text-right">
                  {s.label ?? rankerLabel(s.ranker)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.recall}>
                <td className="pr-2">{row.recall?.toFixed(1)}</td>
                {series.map((s) => (
                  <td key={s.ranker} className="tabular pr-2 text-right">
                    {row[s.ranker] !== undefined ? fmt3(row[s.ranker] ?? 0) : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="recall" type="number" domain={UNIT_DOMAIN} ticks={RECALL_TICKS} {...AXIS} label={{ value: t("recall"), position: "insideBottomRight", dy: 12, fill: "var(--text-tertiary)", fontSize: 12 }} />
          <YAxis domain={UNIT_DOMAIN} {...AXIS} label={{ value: t("precision"), angle: -90, position: "insideLeft", dx: 18, fill: "var(--text-tertiary)", fontSize: 12 }} />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(value: number, name: string, item) => {
              const payload = item.payload as Record<string, number>;
              const n = payload[`${name}__n`];
              return [n !== undefined ? `${fmt3(value)} (n=${n})` : fmt3(value), rankerLabel(name)];
            }}
            labelFormatter={(label: number) => `${t("recall")} ${label.toFixed(1)}`}
          />
          <Legend formatter={(value: string) => rankerLabel(value)} wrapperStyle={{ fontSize: 12 }} />
          {series.map((s) => (
            <Line
              key={s.ranker}
              type="monotone"
              dataKey={s.ranker}
              name={s.ranker}
              stroke={rankerColor(s.ranker)}
              strokeWidth={ghost ? 1.5 : 2.25}
              strokeDasharray={ghost ? "4 4" : rankerDash(s.ranker)}
              strokeOpacity={ghost ? 0.6 : 1}
              dot={{ r: 3, strokeWidth: 0, fill: rankerColor(s.ranker) }}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
