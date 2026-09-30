import { Dialog as RDialog, DropdownMenu as RMenu, Popover as RPopover, Slider as RSlider, Switch as RSwitch, Tooltip as RTooltip } from 'radix-ui'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}

// ------------------------------------------------------------------ buttons

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const variants: Record<Variant, string> = {
  primary: 'bg-accent text-accent-ink hover:bg-accent-hover disabled:opacity-50',
  secondary: 'bg-surface text-ink border border-line hover:border-line-strong hover:bg-sunken disabled:opacity-50',
  ghost: 'text-ink-muted hover:text-ink hover:bg-sunken disabled:opacity-40',
  danger: 'bg-danger text-white hover:opacity-90',
}

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' }
>(function Button({ variant = 'secondary', size = 'md', className, ...props }, ref) {
  return (
    <button
      ref={ref}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors select-none',
        size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-9 px-3.5 text-sm',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
})

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean; size?: 'sm' | 'md' | 'lg' }
>(function IconButton({ label, active, size = 'md', className, children, ...props }, ref) {
  const dim = size === 'lg' ? 'h-12 w-12' : size === 'sm' ? 'h-8 w-8' : 'h-9 w-9'
  return (
    <Tip label={label}>
      <button
        ref={ref}
        aria-label={label}
        className={cx(
          'inline-flex shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-40',
          dim,
          active ? 'bg-accent-soft text-accent-soft-ink' : 'text-ink-muted hover:bg-sunken hover:text-ink',
          className,
        )}
        {...props}
      >
        {children}
      </button>
    </Tip>
  )
})

// ------------------------------------------------------------------ tooltip

export function Tip({ label, children, side = 'top' }: { label: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <RTooltip.Root delayDuration={400}>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content
          side={side}
          sideOffset={6}
          className="fade-in z-50 rounded-md bg-ink px-2 py-1 text-xs text-paper shadow-float"
        >
          {label}
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  )
}

export const TooltipProvider = RTooltip.Provider

// ------------------------------------------------------------------ popover

export function Popover({
  trigger,
  children,
  align = 'center',
  side = 'top',
  className,
  open,
  onOpenChange,
}: {
  trigger: ReactNode
  children: ReactNode
  align?: 'start' | 'center' | 'end'
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  return (
    <RPopover.Root open={open} onOpenChange={onOpenChange}>
      <RPopover.Trigger asChild>{trigger}</RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content
          side={side}
          align={align}
          sideOffset={10}
          collisionPadding={12}
          className={cx('fade-in z-40 rounded-xl border border-line bg-surface p-4 shadow-float outline-none', className)}
        >
          {children}
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  )
}

// ------------------------------------------------------------------ menu

export interface MenuItem {
  label: string
  icon?: ReactNode
  shortcut?: string
  danger?: boolean
  onSelect: () => void
}

export function Menu({ trigger, items, align = 'end', label }: { trigger: ReactNode; items: MenuItem[]; align?: 'start' | 'end'; label: string }) {
  return (
    <RMenu.Root modal={false}>
      <RMenu.Trigger asChild aria-label={label}>{trigger}</RMenu.Trigger>
      <RMenu.Portal>
        <RMenu.Content
          align={align}
          sideOffset={6}
          collisionPadding={12}
          className="fade-in z-50 min-w-44 rounded-xl border border-line bg-surface p-1 shadow-float outline-none"
        >
          {items.map((item, i) => (
            <div key={item.label}>
              {item.danger && i > 0 && <RMenu.Separator className="mx-1 my-1 h-px bg-line" />}
              <RMenu.Item
                onSelect={item.onSelect}
                className={cx(
                  'flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] outline-none select-none',
                  item.danger ? 'text-danger data-[highlighted]:bg-danger-soft' : 'text-ink data-[highlighted]:bg-sunken',
                )}
              >
                {item.icon && <span className={cx('shrink-0', item.danger ? 'text-danger' : 'text-ink-muted')}>{item.icon}</span>}
                <span className="flex-1">{item.label}</span>
                {item.shortcut && <span className="text-[11.5px] text-ink-faint">{item.shortcut}</span>}
              </RMenu.Item>
            </div>
          ))}
        </RMenu.Content>
      </RMenu.Portal>
    </RMenu.Root>
  )
}

// ------------------------------------------------------------------ slider

export function Slider({
  value,
  min,
  max,
  step,
  onChange,
  label,
  format,
  marks,
}: {
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  label: string
  format?: (v: number) => string
  marks?: number[]
}) {
  return (
    <div className="grid gap-2">
      <div className="flex items-baseline justify-between text-[13px]">
        <span className="text-ink">{label}</span>
        <span className="text-ink-muted tabular-nums">{format ? format(value) : value}</span>
      </div>
      <RSlider.Root
        className="relative flex h-5 w-full touch-none items-center select-none"
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => onChange(v[0] ?? value)}
        aria-label={label}
      >
        <RSlider.Track className="relative h-1 grow rounded-full bg-line">
          <RSlider.Range className="absolute h-full rounded-full bg-accent" />
        </RSlider.Track>
        {marks?.map((m) => (
          <span
            key={m}
            className="pointer-events-none absolute h-2 w-px bg-line-strong"
            style={{ left: `${((m - min) / (max - min)) * 100}%` }}
          />
        ))}
        <RSlider.Thumb className="block h-4 w-4 rounded-full border-2 border-accent bg-surface shadow-sm focus-visible:outline-2 focus-visible:outline-accent" />
      </RSlider.Root>
    </div>
  )
}

// ------------------------------------------------------------------ switch

export function Switch({ checked, onChange, label, description, hideLabel }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; hideLabel?: boolean }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span className={hideLabel ? 'sr-only' : 'grid gap-0.5'}>
        <span className="text-[13px] text-ink">{label}</span>
        {description && <span className="text-[12.5px] leading-snug text-ink-muted">{description}</span>}
      </span>
      <RSwitch.Root
        checked={checked}
        onCheckedChange={onChange}
        className="relative mt-0.5 h-5 w-9 shrink-0 rounded-full bg-line-strong transition-colors data-[state=checked]:bg-accent"
      >
        <RSwitch.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
      </RSwitch.Root>
    </label>
  )
}

// ------------------------------------------------------------------ segmented control

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  label: string
}) {
  return (
    <div className="grid gap-2">
      <span className="text-[13px] text-ink">{label}</span>
      <div role="radiogroup" aria-label={label} className="flex rounded-lg bg-sunken p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cx(
              'h-8 flex-1 rounded-md px-2 text-[13px] transition-colors',
              value === o.value ? 'bg-surface text-ink shadow-sm' : 'text-ink-muted hover:text-ink',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ sheet (right panel)

export function Sheet({
  open,
  onOpenChange,
  title,
  children,
  width = 'max-w-[760px]',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  children: ReactNode
  width?: string
}) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fade-in fixed inset-0 z-40 bg-ink/20 dark:bg-black/50" />
        <RDialog.Content
          className={cx(
            'sheet-in fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-paper shadow-float outline-none',
            width,
          )}
          aria-describedby={undefined}
        >
          <RDialog.Title className="sr-only">{title}</RDialog.Title>
          {children}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}

export function Modal({ open, onOpenChange, title, children }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: ReactNode }) {
  return (
    <RDialog.Root open={open} onOpenChange={onOpenChange}>
      <RDialog.Portal>
        <RDialog.Overlay className="fade-in fixed inset-0 z-50 bg-ink/25 dark:bg-black/60" />
        <RDialog.Content
          aria-describedby={undefined}
          className="fade-in fixed top-1/2 left-1/2 z-50 max-h-[88dvh] w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-line bg-surface p-6 shadow-float outline-none"
        >
          <RDialog.Title className="mb-4 text-base font-semibold text-ink">{title}</RDialog.Title>
          {children}
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}

export const DialogClose = RDialog.Close

// ------------------------------------------------------------------ misc

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line bg-surface px-1 font-sans text-[11px] text-ink-muted">
      {children}
    </kbd>
  )
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cx('spin h-4 w-4', className)} aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-[13px] text-ink">{label}</span>
      {children}
      {hint && <span className="text-[12px] text-ink-muted">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none'
