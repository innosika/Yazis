/**
 * Apple-style segmented control: a radio group with roving focus and a sliding indicator.
 */
import { motion, useReducedMotion } from "motion/react";
import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "@/lib/format";

export interface SegmentOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  hint?: string;
  /** Optional swatch colour shown before the label (ranker colours). */
  color?: string;
}

interface Props<T extends string> {
  options: ReadonlyArray<SegmentOption<T>>;
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  size?: "sm" | "md";
  className?: string;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  size = "md",
  className,
}: Props<T>) {
  const layoutId = useId();
  const reduced = useReducedMotion();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const enabled = options.map((o, i) => ({ o, i })).filter(({ o }) => !o.disabled);

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const position = enabled.findIndex((e) => e.i === index);
    if (position === -1) return;
    let next = position;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (position + 1) % enabled.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp")
      next = (position - 1 + enabled.length) % enabled.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = enabled.length - 1;
    else return;
    event.preventDefault();
    const target = enabled[next];
    if (!target) return;
    onChange(target.o.value);
    refs.current[target.i]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cx(
        "inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-pill bg-surface-sunken p-1",
        className,
      )}
    >
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={option.disabled || undefined}
            tabIndex={selected ? 0 : -1}
            title={option.hint}
            disabled={option.disabled}
            onClick={() => !option.disabled && onChange(option.value)}
            onKeyDown={(event) => move(event, index)}
            className={cx(
              "relative shrink-0 whitespace-nowrap rounded-pill font-medium transition-colors",
              size === "sm" ? "px-3 py-1 text-caption" : "px-3.5 py-1.5 text-[14px]",
              selected ? "text-text" : "text-text-secondary hover:text-text",
              option.disabled && "cursor-not-allowed opacity-40 hover:text-text-secondary",
            )}
          >
            {selected && (
              <motion.span
                layoutId={layoutId}
                aria-hidden
                className="absolute inset-0 rounded-pill bg-surface shadow-sm"
                transition={
                  reduced ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 40 }
                }
              />
            )}
            <span className="relative inline-flex items-center gap-1.5">
              {option.color && (
                <span
                  aria-hidden
                  className="size-2 rounded-full"
                  style={{ background: option.color }}
                />
              )}
              {option.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
