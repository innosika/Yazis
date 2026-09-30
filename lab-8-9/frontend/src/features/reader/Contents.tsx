import { cx } from '@/components/ui/primitives'
import type { DocumentFull } from '@/lib/types'
import { usePlayer } from '@/stores/player'

export function Contents({ doc }: { doc: DocumentFull }) {
  const block = usePlayer((s) => s.block)
  const sections = doc.structure.sections
  if (sections.length < 2) return <div className="hidden w-[240px] shrink-0 xl:block" />
  let current = -1
  sections.forEach((s, i) => {
    if (s.block <= block) current = i
  })
  return (
    <nav aria-label="Contents" className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-[240px] shrink-0 overflow-y-auto py-14 pr-5 scroll-thin xl:block">
      <h2 className="mb-3 pl-3 text-[13px] font-semibold text-ink">Contents</h2>
      <ol className="grid gap-px border-l border-line">
        {sections.map((s, i) => (
          <li key={`${s.block}-${i}`}>
            <button
              onClick={() => {
                const p = usePlayer.getState()
                const active = p.status === 'playing' || p.status === 'loading'
                void p.jumpToSentence(s.block, 0, active)
                document.getElementById(`block-${s.block}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
              }}
              className={cx(
                '-ml-px block w-full border-l-2 py-1 pr-2 text-left text-[13px] leading-snug transition-colors',
                s.level > 1 ? 'pl-6' : 'pl-3',
                i === current ? 'border-accent text-ink' : 'border-transparent text-ink-muted hover:text-ink',
              )}
            >
              {s.title}
            </button>
          </li>
        ))}
      </ol>
    </nav>
  )
}
