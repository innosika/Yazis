import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ScoreStep } from "@/lib/api";
import { AXIS, TOOLTIP_STYLE, fmt3 } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

/** Which query term earned how much of the scalar product. */
export function ContributionChart({ steps }: { steps: ScoreStep[] }) {
  const data = steps.map((step) => ({ lemma: step.lemma, share: step.share, product: step.product }));
  return (
    <ChartFrame
      title={t("Contribution of each query term")}
      ariaLabel={t("Bar chart of each query term's share of the scalar product")}
      height={Math.max(120, 28 * data.length + 40)}
      caption={t("Share of (D, Q) contributed by each matched query term.")}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <XAxis type="number" domain={[0, 1]} tickFormatter={(v: number) => `${Math.round(v * 100)}%`} {...AXIS} />
          <YAxis type="category" dataKey="lemma" width={110} {...AXIS} />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(value: number, _name, item) => [
              `${(value * 100).toFixed(1)}% (product ${fmt3((item.payload as { product: number }).product)})`,
              t("share"),
            ]}
          />
          <Bar dataKey="share" radius={[0, 6, 6, 0]} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.lemma} fill="var(--accent)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
