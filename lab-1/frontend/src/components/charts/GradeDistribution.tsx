import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { GRADE_META, GRADE_ORDER } from "@/lib/grades";
import { AXIS, TOOLTIP_STYLE } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

/** How the judged pairs split across ROMIP's five grades. */
export function GradeDistribution({ counts, title = t("Judgment grades") }: { counts: Record<string, number>; title?: string }) {
  const data = [{ name: "grades", ...Object.fromEntries(GRADE_ORDER.map((g) => [g, counts[g] ?? 0])) }];
  const total = GRADE_ORDER.reduce((sum, g) => sum + (counts[g] ?? 0), 0);
  return (
    <ChartFrame title={title} ariaLabel={t("Distribution of relevance grades")} height={96} caption={t("{n} judged pairs. Grades ≥ relevant− count as relevant at the official threshold.", { n: total })}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
          <XAxis type="number" hide domain={[0, Math.max(total, 1)]} />
          <YAxis type="category" dataKey="name" hide {...AXIS} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(value: number, name: string) => [value, t(GRADE_META[name]?.short ?? name)]} />
          {GRADE_ORDER.map((grade) => {
            const level = GRADE_META[grade]?.level;
            return <Bar key={grade} dataKey={grade} stackId="g" fill={level == null ? "var(--hairline-strong)" : `var(--relevance-${level})`} isAnimationActive={false} />;
          })}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
