import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { t } from "@/lib/i18n";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  helpAnchor,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  helpAnchor?: string;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        {eyebrow && (
          <p className="mb-1 text-caption font-medium uppercase tracking-wide text-text-tertiary">{eyebrow}</p>
        )}
        <h1 className="text-title text-balance sm:text-headline">{title}</h1>
        {description && <p className="mt-2 text-[15px] text-text-secondary sm:text-body">{description}</p>}
        {helpAnchor && (
          <Link to="/help" hash={helpAnchor} className="mt-2 inline-block text-caption text-accent hover:underline">
            {t("Help for this screen →")}
          </Link>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
