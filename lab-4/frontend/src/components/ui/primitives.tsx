/**
 * The design system's primitives.
 *
 * Kept in one file because each is a handful of lines and they are always used together;
 * splitting them across ten modules would add imports without adding clarity.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { useId, useState } from 'react'

import { classes } from '@/lib/format'

/* ------------------------------------------------------------------------------ Button */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-accent-ink hover:bg-accent-hover border-transparent shadow-[inset_0_1px_0_rgba(255,255,255,0.12)]',
  secondary: 'bg-surface text-ink border-line-strong hover:bg-sunken',
  ghost: 'bg-transparent text-ink-muted border-transparent hover:bg-sunken hover:text-ink',
  danger: 'bg-transparent text-danger border-line hover:bg-danger-soft',
}

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  busy = false,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  busy?: boolean
}) {
  return (
    <button
      type="button"
      {...rest}
      disabled={rest.disabled || busy}
      aria-busy={busy || undefined}
      className={classes(
        'inline-flex shrink-0 items-center justify-center rounded-md border font-medium',
        'transition-colors duration-100 disabled:cursor-not-allowed disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
    >
      {busy && <Spinner className="size-3.5" />}
      {children}
    </button>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={classes('animate-spin', className)} viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path
        d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

/* -------------------------------------------------------------------------------- Card */

export function Card({
  children,
  className,
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div' | 'article'
}) {
  return (
    <Tag className={classes('rounded-lg border border-line bg-surface', className)}>{children}</Tag>
  )
}

export function CardHeader({
  title,
  hint,
  actions,
  subtitle,
}: {
  title: ReactNode
  hint?: string
  actions?: ReactNode
  subtitle?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
      <div className="min-w-0">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          {title}
          {hint && <Hint text={hint} />}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}

/* -------------------------------------------------------------------------------- Hint */

/**
 * The «?» tooltip the assignment asks for: "the interface must be simple and accessible
 * for users of any level". Implemented with a native popover-free approach - a button that
 * toggles a panel - so it works on touch as well as hover and is reachable by keyboard.
 */
export function Hint({ text, label = 'What is this?' }: { text: string; label?: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span className="relative inline-flex no-print">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((value) => !value)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onBlur={() => setOpen(false)}
        className="grid size-4 place-items-center rounded-full border border-line-strong text-[10px] font-bold text-ink-faint transition-colors hover:border-accent hover:text-accent"
      >
        ?
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute top-6 left-0 z-40 w-64 rounded-md border border-line bg-surface p-2.5 text-xs leading-relaxed font-normal text-ink-muted shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  )
}

/* ------------------------------------------------------------------------------- Badge */

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'source' | 'target'

const TONES: Record<Tone, string> = {
  neutral: 'bg-sunken text-ink-muted border-line',
  accent: 'bg-accent-soft text-accent-soft-ink border-transparent',
  success: 'bg-success-soft text-success border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
  danger: 'bg-danger-soft text-danger border-transparent',
  info: 'bg-info-soft text-info border-transparent',
  source: 'bg-source text-source-ink border-source-line',
  target: 'bg-target text-target-ink border-target-line',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  title,
  mono = false,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  title?: string
  mono?: boolean
}) {
  return (
    <span
      title={title}
      className={classes(
        'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap',
        mono && 'font-mono',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/* ------------------------------------------------------------------------------ Fields */

export function Field({
  label,
  hint,
  children,
  htmlFor,
  className,
}: {
  label: string
  hint?: string
  children: ReactNode
  htmlFor?: string
  className?: string
}) {
  return (
    <div className={classes('flex flex-col gap-1.5', className)}>
      <label
        htmlFor={htmlFor}
        className="flex items-center gap-1.5 text-xs font-medium text-ink-muted"
      >
        {label}
        {hint && <Hint text={hint} />}
      </label>
      {children}
    </div>
  )
}

const CONTROL =
  'w-full rounded-md border border-line-strong bg-surface px-2.5 text-sm text-ink placeholder:text-ink-faint transition-colors focus:border-accent disabled:opacity-50'

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={classes(CONTROL, 'h-9', props.className)} />
}

export function Select({
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select {...rest} className={classes(CONTROL, 'h-9 cursor-pointer pr-8', rest.className)}>
      {children}
    </select>
  )
}

/** A segmented control: the right shape for two or three mutually exclusive choices. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string; title?: string }[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-md border border-line-strong bg-sunken p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={classes(
              'rounded px-2.5 py-1 text-xs font-medium transition-colors',
              active
                ? 'bg-surface text-ink shadow-sm'
                : 'text-ink-muted hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

/* -------------------------------------------------------------------------------- Tabs */

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { value: T; label: string; count?: number; hint?: string }[]
  active: T
  onChange: (value: T) => void
}) {
  return (
    <div role="tablist" className="flex gap-0.5 overflow-x-auto scroll-thin no-print">
      {tabs.map((tab) => {
        const selected = tab.value === active
        return (
          <button
            key={tab.value}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(tab.value)}
            title={tab.hint}
            className={classes(
              'relative flex items-center gap-1.5 whitespace-nowrap px-3 py-2 text-[13px] font-medium transition-colors',
              selected
                ? 'text-accent after:absolute after:inset-x-1 after:-bottom-px after:h-0.5 after:rounded-full after:bg-accent'
                : 'text-ink-muted hover:text-ink',
            )}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span className="nums rounded bg-sunken px-1 text-[10px] text-ink-faint">
                {tab.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------------------ States */

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div role="status" className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {body && <p className="max-w-sm text-xs leading-relaxed text-ink-muted">{body}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 px-6 py-10 text-center">
      <div className="flex items-center gap-2 text-sm font-medium text-danger">
        <svg viewBox="0 0 16 16" className="size-4" aria-hidden="true" fill="currentColor">
          <path d="M8 1.5 15 14H1L8 1.5Zm0 4v4.2m0 1.6v1.2" stroke="currentColor" strokeWidth="1.3" fill="none" />
        </svg>
        Something went wrong
      </div>
      <p className="max-w-md text-xs leading-relaxed text-ink-muted">{message}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function Skeleton({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={classes('space-y-2 p-4', className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="h-4 animate-pulse rounded bg-sunken"
          style={{ width: `${88 - index * 9}%` }}
        />
      ))}
    </div>
  )
}

/** A banner for an error that happened during an action, not during a load. */
export function InlineError({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-danger"
    >
      <span className="flex-1 leading-relaxed">{message}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Dismiss" className="font-bold">
          ×
        </button>
      )}
    </div>
  )
}
