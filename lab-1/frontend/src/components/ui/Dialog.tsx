/**
 * Native <dialog>-based modal and side sheet: the browser traps focus and handles Escape.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "@/lib/format";
import { Button } from "./Button";
import { t } from "@/lib/i18n";

interface Props {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  side?: "center" | "right";
  width?: string;
}

export function Dialog({ open, onClose, title, description, children, side = "center", width }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
      aria-labelledby="dialog-title"
      className={cx(
        "m-0 max-h-none max-w-none bg-transparent p-0 text-text backdrop:bg-black/40 backdrop:backdrop-blur-sm",
        side === "center" && "fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
        side === "right" && "fixed inset-y-0 right-0 left-auto h-screen translate-x-0 translate-y-0",
      )}
    >
      <div
        className={cx(
          "flex flex-col overflow-hidden border border-hairline bg-surface shadow-lg",
          side === "center" && "max-h-[85vh] w-[min(92vw,36rem)] rounded-panel",
          side === "right" && "h-full w-[min(100vw,42rem)] rounded-l-panel",
        )}
        style={width ? { width } : undefined}
      >
        <header className="hairline-b flex items-start justify-between gap-4 px-5 py-4">
          <div className="min-w-0">
            <h2 id="dialog-title" className="text-[17px] font-semibold tracking-tight">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-caption text-text-secondary">{description}</p>}
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label={t("Close")}>
            ✕
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </dialog>
  );
}

export function Sheet(props: Omit<Props, "side">) {
  return <Dialog side="right" {...props} />;
}
