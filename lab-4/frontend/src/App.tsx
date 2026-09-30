import { ErrorState, Skeleton } from '@/components/ui/primitives'
import { TopBar } from '@/components/layout/TopBar'
import { MetaProvider } from '@/lib/meta'
import { useRoute } from '@/lib/router'
import { useTheme } from '@/lib/theme'
import { DictionaryPage } from '@/pages/DictionaryPage'
import { HelpPage } from '@/pages/HelpPage'
import { MemoryPage } from '@/pages/MemoryPage'
import { TranslatePage } from '@/pages/TranslatePage'

export function App() {
  const [route, navigate] = useRoute()
  const [theme, toggleTheme] = useTheme()

  return (
    <MetaProvider>
      {({ ready, error }) => (
        <div className="flex min-h-dvh flex-col">
          <TopBar route={route} onNavigate={navigate} theme={theme} onToggleTheme={toggleTheme} />

          <main className="mx-auto w-full max-w-[1680px] flex-1 px-4 py-5 sm:px-6">
            {error && !ready ? (
              <ErrorState message={error} onRetry={() => window.location.reload()} />
            ) : !ready ? (
              <Skeleton rows={6} />
            ) : (
              <>
                {route === 'translate' && <TranslatePage />}
                {route === 'dictionary' && <DictionaryPage />}
                {route === 'memory' && <MemoryPage />}
                {route === 'help' && <HelpPage />}
              </>
            )}
          </main>

          <footer className="border-t border-line px-4 py-4 text-[11px] leading-relaxed text-ink-faint sm:px-6 no-print">
            <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-2">
              <span>
                Laboratory work 4 — automatic machine translation of texts, variant 1 (English →
                Russian; computer-science articles and literary essays).
              </span>
              <span>
                Dictionary: FreeDict eng-rus (CC BY-SA 3.0) · Analysis: spaCy · Russian morphology:
                pymorphy3 / OpenCorpora
              </span>
            </div>
          </footer>
        </div>
      )}
    </MetaProvider>
  )
}
