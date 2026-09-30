import { Badge, Button } from '@/components/ui/primitives'
import { classes, thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { ROUTES, type Route } from '@/lib/router'
import type { Theme } from '@/lib/theme'

const LABELS: Record<Route, string> = {
  translate: 'Translate',
  dictionary: 'Dictionary',
  memory: 'Memory',
  help: 'Help',
}

export function TopBar({
  route,
  onNavigate,
  theme,
  onToggleTheme,
}: {
  route: Route
  onNavigate: (route: Route) => void
  theme: Theme
  onToggleTheme: () => void
}) {
  const { meta } = useMeta()

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/85 backdrop-blur-md no-print">
      <div className="mx-auto flex h-14 max-w-[1680px] items-center gap-4 px-4 sm:px-6">
        <a
          href="#/translate"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="MT Workbench, home"
        >
          <span
            aria-hidden="true"
            className="grid size-8 place-items-center rounded-md bg-accent text-[13px] font-bold tracking-tight text-accent-ink"
          >
            <span>
              A<span className="opacity-60">Я</span>
            </span>
          </span>
          <span className="hidden flex-col leading-tight sm:flex">
            <span className="text-sm font-semibold text-ink">MT Workbench</span>
            <span className="text-[11px] text-ink-faint">English → Russian</span>
          </span>
        </a>

        <nav aria-label="Main" className="flex flex-1 items-center gap-0.5 overflow-x-auto scroll-thin">
          {ROUTES.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => onNavigate(name)}
              aria-current={route === name ? 'page' : undefined}
              className={classes(
                'rounded-md px-3 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors',
                route === name
                  ? 'bg-accent-soft text-accent-soft-ink'
                  : 'text-ink-muted hover:bg-sunken hover:text-ink',
              )}
            >
              {LABELS[name]}
            </button>
          ))}
        </nav>

        {meta && (
          <Badge
            tone="neutral"
            className="hidden lg:inline-flex"
            title={`${thousands(meta.dictionary.entries)} headwords, ${thousands(
              meta.dictionary.senses,
            )} senses, ${thousands(meta.dictionary.translations)} Russian equivalents`}
          >
            <span className="nums">{thousands(meta.dictionary.entries)}</span> entries
          </Badge>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </Button>
      </div>
    </header>
  )
}

function SunIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <circle cx="8" cy="8" r="3.1" />
      <path strokeLinecap="round" d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3.1 3.1l1.1 1.1M11.8 11.8l1.1 1.1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path strokeLinecap="round" d="M13.3 9.7A5.8 5.8 0 0 1 6.3 2.7a5.8 5.8 0 1 0 7 7Z" />
    </svg>
  )
}
