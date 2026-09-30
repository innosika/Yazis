import type { ReactNode } from "react";
import { cx } from "@/lib/format";
import { t } from "@/lib/i18n";

interface Props {
  title?: ReactNode;
  caption?: ReactNode;
  legend?: ReactNode;
  /** Recharts' ResponsiveContainer needs a sized parent: the height is fixed here. */
  height?: number;
  ariaLabel: string;
  children: ReactNode;
  className?: string;
  /** Accessible data table shown under a disclosure. */
  table?: ReactNode;
}

export function ChartFrame({
  title,
  caption,
  legend,
  height = 288,
  ariaLabel,
  children,
  className,
  table,
}: Props) {
  return (
    <figure className={cx("rounded-card border border-hairline bg-surface p-4 shadow-sm", className)}>
      {(title || legend) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          {title && <figcaption className="text-[15px] font-semibold tracking-tight text-text">{title}</figcaption>}
          {legend && <div className="flex flex-wrap items-center gap-2 text-caption text-text-secondary">{legend}</div>}
        </div>
      )}
      <div role="img" aria-label={ariaLabel} style={{ height }} className="w-full">
        {children}
      </div>
      {caption && <p className="mt-3 text-caption text-text-tertiary">{caption}</p>}
      {table && (
        <details className="mt-2 text-caption text-text-secondary">
          <summary className="cursor-pointer">{t("Show the data")}</summary>
          <div className="mt-2 overflow-x-auto">{table}</div>
        </details>
      )}
    </figure>
  );
}
