import type { ReactNode } from "react";

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex min-w-5 items-center justify-center rounded border border-hairline-strong bg-surface-sunken px-1.5 font-mono text-[11px] text-text-secondary">
      {children}
    </kbd>
  );
}
