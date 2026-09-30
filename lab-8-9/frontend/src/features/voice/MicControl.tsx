import { History, Mic, MicOff } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { cx, Popover, Spinner, Tip } from '@/components/ui/primitives'
import { useSettings } from '@/stores/settings'
import { micLevel, useVoice } from '@/stores/voice'
import { startListening, stopListening, talkEnd, talkStart, talkTap } from '@/voice/controller'

import { ActivityPanel } from './ActivityPanel'

const LABELS: Record<string, string> = {
  off: '',
  starting: 'Starting…',
  listening: 'Listening',
  hearing: 'Hearing you',
  recognizing: 'Recognizing…',
  error: 'Microphone blocked',
}

export function MicControl() {
  const mic = useVoice((s) => s.mic)
  const mode = useSettings((s) => s.profile.listening.mode)
  const ring = useRef<HTMLSpanElement>(null)
  const pressedAt = useRef(0)
  const holdTimer = useRef(0)
  const holding = useRef(false)

  useEffect(
    () =>
      micLevel.subscribe((level) => {
        if (ring.current) ring.current.style.transform = `scale(${1 + Math.min(1, level) * 0.45})`
      }),
    [],
  )

  const live = mic === 'listening' || mic === 'hearing' || mic === 'recognizing' || mic === 'starting'
  const label = mode === 'push-to-talk' && mic === 'off' ? 'Hold M or tap to talk' : mode === 'hands-free' && mic === 'off' ? 'Voice off' : LABELS[mic]

  // Push-to-talk: a long press holds the mic open, a short tap listens for one command.
  const down = () => {
    if (mode !== 'push-to-talk') return
    pressedAt.current = performance.now()
    holdTimer.current = window.setTimeout(() => {
      holding.current = true
      void talkStart()
    }, 280)
  }
  const up = () => {
    if (mode !== 'push-to-talk') return
    window.clearTimeout(holdTimer.current)
    if (holding.current) {
      holding.current = false
      void talkEnd()
    } else if (performance.now() - pressedAt.current < 280) {
      void talkTap()
    }
  }
  const click = () => {
    if (mode === 'hands-free') void (mic === 'off' || mic === 'error' ? startListening() : stopListening())
  }

  const tip = mode === 'push-to-talk'
    ? 'Hold to talk, or tap and say one command. Keyboard: hold M.'
    : mic === 'off' ? 'Start listening for commands (M)' : 'Stop listening (M)'

  return (
    <div className="flex items-center gap-1 pl-1">
      <span className="hidden max-w-36 truncate text-right text-[12.5px] text-ink-muted lg:block" aria-hidden>
        {label}
      </span>
      <Tip label={tip}>
        <button
          aria-label={tip}
          aria-pressed={live}
          onPointerDown={down}
          onPointerUp={up}
          onPointerLeave={() => { if (holding.current) up() ; window.clearTimeout(holdTimer.current) }}
          onClick={click}
          onContextMenu={(e) => e.preventDefault()}
          className={cx(
            'relative flex h-11 w-11 shrink-0 touch-none items-center justify-center rounded-full transition-colors select-none',
            live ? 'bg-live text-white' : mic === 'error' ? 'bg-danger-soft text-danger' : 'bg-sunken text-ink hover:bg-line',
          )}
        >
          {live && (
            <span
              ref={ring}
              aria-hidden
              className={cx('absolute inset-0 rounded-full bg-live/40 transition-transform duration-75', mic === 'listening' && 'orb-breathe')}
            />
          )}
          <span className="relative">
            {mic === 'recognizing' || mic === 'starting' ? <Spinner className="h-[18px] w-[18px]" /> : mic === 'error' ? <MicOff size={18} /> : <Mic size={18} />}
          </span>
        </button>
      </Tip>
      <Popover
        align="end"
        className="w-[min(420px,calc(100vw-24px))] p-0"
        trigger={
          <button aria-label="Voice activity" className="hidden h-9 w-9 items-center justify-center rounded-full text-ink-muted hover:bg-sunken hover:text-ink sm:inline-flex">
            <History size={17} />
          </button>
        }
      >
        <ActivityPanel />
      </Popover>
    </div>
  )
}
