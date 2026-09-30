import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cx } from "@/lib/format";

/** Every table scrolls inside its own container so the page never scrolls sideways. */
export function TableFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0", className)}>{children}</div>
  );
}

export function Table({ className, children, ...rest }: HTMLAttributes<HTMLTableElement>) {
  return (
    <table className={cx("w-full border-collapse text-[14px]", className)} {...rest}>
      {children}
    </table>
  );
}

interface ThProps extends ThHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
  sortable?: boolean;
  sorted?: "asc" | "desc" | null;
  onSort?: () => void;
  help?: ReactNode;
}

export function Th({ numeric, sortable, sorted, onSort, help, className, children, ...rest }: ThProps) {
  const content = (
    <span className="inline-flex items-center gap-1">
      {children}
      {help}
      {sortable && (
        <span aria-hidden className="text-text-tertiary">
          {sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : "↕"}
        </span>
      )}
    </span>
  );
  return (
    <th
      scope="col"
      aria-sort={sorted ? (sorted === "asc" ? "ascending" : "descending") : undefined}
      className={cx(
        "hairline-b whitespace-nowrap py-2 pr-3 text-left text-caption font-medium text-text-secondary",
        numeric && "text-right",
        className,
      )}
      {...rest}
    >
      {sortable ? (
        <button type="button" onClick={onSort} className="rounded hover:text-text">
          {content}
        </button>
      ) : (
        content
      )}
    </th>
  );
}

interface TdProps extends TdHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
  strong?: boolean;
}

export function Td({ numeric, strong, className, children, ...rest }: TdProps) {
  return (
    <td
      className={cx(
        "hairline-b py-2 pr-3 align-top text-text",
        numeric && "tabular text-right",
        strong && "font-semibold",
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}
