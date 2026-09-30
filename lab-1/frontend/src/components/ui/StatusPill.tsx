import { cx } from "@/lib/format";

interface Props {
  ok: boolean | undefined;
  label: string;
  detail?: string | null;
}

/** Compact dependency indicator used in the header and on the readiness panel. */
export function StatusPill({ ok, label, detail }: Props) {
  return (
    <span
      title={detail ?? undefined}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-1 text-caption",
        ok === undefined
          ? "border-hairline text-text-tertiary"
          : ok
            ? "border-positive/30 text-positive"
            : "border-negative/30 text-negative",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "size-1.5 rounded-full",
          ok === undefined ? "bg-text-tertiary" : ok ? "bg-positive" : "bg-negative",
        )}
      />
      {label}
    </span>
  );
}
