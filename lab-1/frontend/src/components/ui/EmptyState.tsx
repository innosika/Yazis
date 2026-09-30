import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-hairline-strong px-6 py-12 text-center">
      {icon && <div className="text-3xl text-text-tertiary">{icon}</div>}
      <h3 className="text-[17px] font-semibold text-text">{title}</h3>
      {description && <p className="max-w-md text-[15px] text-text-secondary">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
