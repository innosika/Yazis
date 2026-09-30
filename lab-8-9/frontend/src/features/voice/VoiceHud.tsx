import { CircleAlert, CircleCheck, Ear, Info } from 'lucide-react'

import { cx } from '@/components/ui/primitives'
import { useVoice } from '@/stores/voice'

/** The one-line account of what the voice system is doing right now. */
export function VoiceHud() {
  const hud = useVoice((s) => s.hud)
  const mic = useVoice((s) => s.mic)
  const live =
    mic === 'hearing' ? { text: 'Hearing you…', tone: 'neutral' as const }
    : mic === 'recognizing' ? { text: 'Recognizing…', tone: 'neutral' as const }
    : null
  const msg = live && !hud ? live : hud
  return (
    <div aria-live="polite" aria-atomic className="mb-2 flex min-h-9 items-end justify-center">
      {msg && (
        <div
          key={'id' in msg ? msg.id : msg.text}
          className={cx(
            'hud-in pointer-events-auto flex max-w-[min(640px,calc(100vw-24px))] items-center gap-2 rounded-full border px-3.5 py-1.5 text-[13px] shadow-float',
            msg.tone === 'error' ? 'border-danger/30 bg-danger-soft text-danger'
            : msg.tone === 'warning' ? 'border-warning/30 bg-warning-soft text-warning'
            : 'border-line bg-surface text-ink',
          )}
        >
          {msg.tone === 'success' ? <CircleCheck size={15} className="shrink-0 text-success" />
            : msg.tone === 'error' || msg.tone === 'warning' ? <CircleAlert size={15} className="shrink-0" />
            : live && !hud ? <Ear size={15} className="shrink-0 text-live" />
            : <Info size={15} className="shrink-0 text-ink-muted" />}
          <span className="truncate">{msg.text}</span>
          {'detail' in msg && msg.detail && (
            <>
              <span aria-hidden className="text-ink-faint">→</span>
              <span className="truncate font-medium">{msg.detail}</span>
            </>
          )}
        </div>
      )}
    </div>
  )
}
