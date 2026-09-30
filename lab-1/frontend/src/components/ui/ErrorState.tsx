import { ApiError } from "@/lib/api";
import { Button } from "./Button";
import { t } from "@/lib/i18n";

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const isApi = error instanceof ApiError;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div
      role="alert"
      className={`rounded-card border border-negative/30 bg-negative/5 text-text ${compact ? "p-3" : "p-5"}`}
    >
      <p className="font-medium text-negative">
        {isApi ? t("Request failed (HTTP {status})", { status: error.status }) : t("Something went wrong")}
      </p>
      <p className="mt-1 text-[15px] text-text-secondary">{message}</p>
      {isApi && error.details !== undefined && !compact && (
        <details className="mt-2 text-caption text-text-tertiary">
          <summary className="cursor-pointer">{t("Details")}</summary>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px]">
            {JSON.stringify(error.details, null, 2)}
          </pre>
        </details>
      )}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          {t("Try again")}
        </Button>
      )}
    </div>
  );
}
