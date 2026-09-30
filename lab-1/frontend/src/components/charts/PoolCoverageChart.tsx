import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PoolTopic } from "@/lib/api";
import { rankerColor, rankerLabel } from "./rankerColor";
import { AXIS, GRID, TOOLTIP_STYLE } from "./chartTheme";
import { ChartFrame } from "./ChartFrame";
import { t } from "@/lib/i18n";

const SOURCE_COLOR: Record<string, string> = {
  run_union: "var(--accent)",
  oracle: "var(--positive)",
  random_sample: "var(--caution)",
  manual_seed: "var(--text-tertiary)",
};
const SOURCE_LABEL: Record<string, string> = {
  run_union: "rankers' top-k",
  oracle: "oracle query only",
  random_sample: "random sample",
  manual_seed: "manual",
};

export function PoolCoverageChart({ topics, mode }: { topics: PoolTopic[]; mode: "source" | "ranker" }) {
  const keys = new Set<string>();
  const data = topics.map((t) => {
    const bucket = mode === "source" ? t.by_source : t.by_ranker;
    for (const k of Object.keys(bucket)) keys.add(k);
    return { ext_id: t.ext_id, title: t.title, ...bucket };
  });
  const ordered = [...keys].sort();
  return (
    <ChartFrame
      title={mode === "source" ? t("Pool provenance per topic") : t("Which rankers contributed to each topic's pool")}
      ariaLabel={t("Stacked bars of pool entries per topic")}
      height={300}
      caption={
        mode === "source"
          ? t("Documents only the oracle query found are the ones every ranker missed; the random sample measures how complete the pool is.")
          : t("A document counts once per ranker that returned it in its top-k, so stacks exceed the pool size.")
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <CartesianGrid {...GRID} vertical={false} />
          <XAxis dataKey="ext_id" {...AXIS} />
          <YAxis {...AXIS} allowDecimals={false} />
          <Tooltip
            {...TOOLTIP_STYLE}
            labelFormatter={(label: number, payload) => {
              const first = payload?.[0]?.payload as { title?: string } | undefined;
              return `${t("topic")} ${label}${first?.title ? ` — ${first.title}` : ""}`;
            }}
            formatter={(value: number, name: string) => [value, mode === "source" ? t(SOURCE_LABEL[name] ?? name) : rankerLabel(name)]}
          />
          <Legend formatter={(value: string) => (mode === "source" ? t(SOURCE_LABEL[value] ?? value) : rankerLabel(value))} wrapperStyle={{ fontSize: 12 }} />
          {ordered.map((key) => (
            <Bar key={key} dataKey={key} stackId="pool" fill={mode === "source" ? SOURCE_COLOR[key] ?? "var(--text-tertiary)" : rankerColor(key)} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
