/**
 * Contextual help: a small "?" that reveals an explanation on hover or focus, with an
 * optional link into the Help screen. Part of the assignment's required help facilities.
 */
import { Link } from "@tanstack/react-router";
import { useId, useState, type ReactNode } from "react";
import { cx } from "@/lib/format";
import { t } from "@/lib/i18n";

interface Props {
  children: ReactNode;
  /** Anchor id on the Help page, e.g. "glossary-map". */
  anchor?: string;
  label?: string;
  className?: string;
}

export function HelpTip({ children, anchor, label = t("Explain"), className }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className={cx("relative inline-flex", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
        className="inline-flex size-4 items-center justify-center rounded-full border border-hairline-strong text-[10px] font-semibold text-text-tertiary hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-1/2 top-full z-40 mt-2 w-72 -translate-x-1/2 rounded-panel border border-hairline bg-surface-raised p-3 text-left text-caption font-normal leading-relaxed text-text shadow-lg"
        >
          {children}
          {anchor && (
            <>
              {" "}
              <Link to="/help" hash={anchor} className="text-accent hover:underline">
                {t("Read more")}
              </Link>
            </>
          )}
        </span>
      )}
    </span>
  );
}
