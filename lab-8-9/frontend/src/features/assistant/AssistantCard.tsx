import { Square, Volume2, X } from 'lucide-react'

import { IconButton, Spinner } from '@/components/ui/primitives'
import { getEngine } from '@/stores/player'
import { useUi } from '@/stores/ui'

export function AssistantCard() {
  const card = useUi((s) => s.assistant)
  const setAssistant = useUi((s) => s.setAssistant)
  if (!card) return null
  const heading = card.kind === 'explain' ? `What “${card.title}” means here` : card.kind === 'summary' ? `Summary of ${card.title}` : card.title
  return (
    <aside
      aria-live="polite"
      className="fade-in fixed right-4 bottom-28 z-30 w-[min(420px,calc(100vw-32px))] rounded-2xl border border-line bg-surface p-4 shadow-float"
    >
      <div className="flex items-start gap-2">
        <h3 className="min-w-0 flex-1 text-[13.5px] font-semibold text-ink">{heading}</h3>
        {card.text && (
          <>
            <IconButton size="sm" label="Read aloud" onClick={() => void getEngine().say(card.text!).catch(() => undefined)}><Volume2 size={15} /></IconButton>
            <IconButton size="sm" label="Stop speaking" onClick={() => getEngine().stopSaying()}><Square size={13} /></IconButton>
          </>
        )}
        <IconButton size="sm" label="Close" onClick={() => { getEngine().stopSaying(); setAssistant(null) }}><X size={15} /></IconButton>
      </div>
      <div className="mt-2 font-serif text-[15px] leading-relaxed text-ink">
        {card.error ? (
          <p className="font-sans text-[13px] text-danger">{card.error}</p>
        ) : card.text ? (
          <p>{card.text}</p>
        ) : (
          <p className="flex items-center gap-2 font-sans text-[13px] text-ink-muted"><Spinner /> Thinking about it…</p>
        )}
      </div>
      <p className="mt-3 text-[11.5px] text-ink-faint">Answered by a language model from the paper’s text; check important details against the source.</p>
    </aside>
  )
}
