import type { ErrorComponentProps } from "@tanstack/react-router";
import { ErrorState } from "@/components/ui/ErrorState";

export function RouteError({ error, reset }: ErrorComponentProps) {
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <ErrorState error={error} onRetry={reset} />
    </main>
  );
}
