import type { ReactNode } from "react";
import { cx } from "@/lib/format";
import { rankerColor, rankerLabel } from "@/components/charts/rankerColor";
import { GRADE_META } from "@/lib/grades";
import { t } from "@/lib/i18n";

type Tone = "neutral" | "accent" | "positive" | "caution" | "negative";

const TONE: Record<Tone, string> = {
  neutral: "border-hairline text-text-secondary",
  accent: "border-accent/30 bg-accent-soft text-accent",
  positive: "border-positive/30 text-positive",
  caution: "border-caution/30 text-caution",
  negative: "border-negative/30 text-negative",
};

export function Badge({
  tone = "neutral",
  color,
  className,
  children,
  title,
}: {
  tone?: Tone;
  color?: string;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill border px-2 py-0.5 text-caption",
        TONE[tone],
        className,
      )}
    >
      {color && <span aria-hidden className="size-2 rounded-full" style={{ background: color }} />}
      {children}
    </span>
  );
}

/** Relevance grade on ROMIP's scale, coloured with the relevance ramp. */
export function GradeBadge({ grade, compact = false }: { grade: string | null | undefined; compact?: boolean }) {
  if (!grade) {
    return (
      <Badge tone="neutral" title={t("not judged")}>
        {t("unjudged")}
      </Badge>
    );
  }
  const meta = GRADE_META[grade];
  if (!meta) return <Badge>{grade}</Badge>;
  const color = meta.level === null ? "var(--hairline-strong)" : `var(--relevance-${meta.level})`;
  return (
    <Badge title={t(meta.label)} color={color} className="border-hairline text-text">
      {compact ? (meta.level ?? "?") : t(meta.short)}
    </Badge>
  );
}

export function RankerBadge({ ranker, label }: { ranker: string; label?: string }) {
  return (
    <Badge color={rankerColor(ranker)} className="border-hairline text-text">
      {label ?? rankerLabel(ranker)}
    </Badge>
  );
}
