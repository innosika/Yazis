import { cx } from "@/lib/format";

export function Skeleton({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden className={cx("animate-pulse space-y-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-3.5 rounded bg-surface-sunken"
          style={{ width: `${100 - ((i * 17) % 40)}%` }}
        />
      ))}
    </div>
  );
}
