import { useId } from "react";
import { cx } from "@/lib/format";

interface Props {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}

export function Toggle({ checked, onChange, label, description, disabled }: Props) {
  const id = useId();
  return (
    <label htmlFor={id} className={cx("flex items-start gap-3", disabled && "opacity-50")}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative mt-0.5 h-6 w-10 shrink-0 rounded-pill transition-colors",
          checked ? "bg-accent" : "bg-hairline-strong",
        )}
      >
        <span
          aria-hidden
          className={cx(
            "absolute top-0.5 size-5 rounded-full bg-white shadow-sm transition-transform",
            checked ? "translate-x-[18px]" : "translate-x-0.5",
          )}
        />
      </button>
      <span className="select-none">
        <span className="block text-[15px] text-text">{label}</span>
        {description && <span className="block text-caption text-text-tertiary">{description}</span>}
      </span>
    </label>
  );
}
