/** Shared Recharts styling so every chart reads as one system. */
export const UNIT_DOMAIN: [number, number] = [0, 1];
export const UNIT_TICKS = [0, 0.2, 0.4, 0.6, 0.8, 1];
export const RECALL_TICKS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];

export const AXIS = {
  stroke: "var(--hairline-strong)",
  tick: { fill: "var(--text-tertiary)", fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: "var(--hairline-strong)" },
} as const;

export const GRID = { stroke: "var(--hairline)", strokeDasharray: "2 4" } as const;

export const TOOLTIP_STYLE = {
  contentStyle: {
    background: "var(--surface-raised)",
    border: "1px solid var(--hairline)",
    borderRadius: 12,
    boxShadow: "var(--shadow-md)",
    color: "var(--text)",
    fontSize: 12,
  },
  labelStyle: { color: "var(--text-secondary)", marginBottom: 4 },
  itemStyle: { color: "var(--text)" },
  cursor: { stroke: "var(--hairline-strong)" },
} as const;

export const fmt3 = (value: number): string => value.toFixed(3);
export const fmt2 = (value: number): string => value.toFixed(2);
