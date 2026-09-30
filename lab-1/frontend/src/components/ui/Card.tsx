import type { HTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/format";

interface Props extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  padding?: "none" | "sm" | "md";
  as?: "section" | "div" | "article";
}

export function Card({
  title,
  subtitle,
  actions,
  padding = "md",
  as: Tag = "section",
  className,
  children,
  ...rest
}: Props) {
  return (
    <Tag
      className={cx(
        "rounded-card border border-hairline bg-surface shadow-sm",
        padding === "md" && "p-5",
        padding === "sm" && "p-3",
        className,
      )}
      {...rest}
    >
      {(title || actions) && (
        <header className={cx("mb-4 flex items-start justify-between gap-4", padding === "none" && "px-5 pt-5")}>
          <div className="min-w-0">
            {title && <h2 className="text-[17px] font-semibold tracking-tight text-text">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-caption text-text-secondary">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}
