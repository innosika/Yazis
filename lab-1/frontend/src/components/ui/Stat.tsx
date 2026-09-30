import type { ReactNode } from "react";

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-card border border-hairline bg-surface p-4 shadow-sm">
      <dt className="text-caption text-text-tertiary">{label}</dt>
      <dd className="tabular mt-1 text-[22px] font-semibold tracking-tight text-text">{value}</dd>
      {hint && <p className="mt-0.5 text-caption text-text-secondary">{hint}</p>}
    </div>
  );
}
