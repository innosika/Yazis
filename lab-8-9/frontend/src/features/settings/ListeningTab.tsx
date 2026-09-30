import { Headphones } from 'lucide-react'

import { Segmented, Slider, Switch } from '@/components/ui/primitives'
import { useHealth, useVoiceStatus } from '@/lib/queries'
import type { Lang } from '@/lib/types'
import { useSettings } from '@/stores/settings'

import { Group, TabBody } from './SettingsSheet'

export const LANGUAGES: { value: Lang; label: string }[] = [
  { value: 'en', label: 'English' },
  { value: 'ru', label: 'Русский' },
  { value: 'de', label: 'Deutsch' },
  { value: 'fr', label: 'Français' },
]

function EngineStatus() {
  const { data: status } = useVoiceStatus()
  const { data: health } = useHealth()
  if (!status || !health) return null
  const cloud = health.groq === 'missing'
    ? 'Cloud recognition is off: add GROQ_API_KEY to .env and run make restart.'
    : status.cloud_available ? 'Cloud recognition (Whisper large-v3-turbo on Groq) is available.'
    : `Cloud recognition is paused: ${status.cloud_issue ?? 'unavailable'}${status.cloud_cooldown_s ? `, back in ${Math.round(status.cloud_cooldown_s)} s` : ''}.`
  const local = status.local_status === 'ready' ? 'The local recogniser (Parakeet 0.6B) is loaded.'
    : status.local_status === 'loading' ? 'The local recogniser is loading…' : `The local recogniser is ${status.local_status}.`
  return (
    <p className="rounded-lg bg-sunken px-3 py-2 text-[12.5px] leading-relaxed text-ink-muted">
      {cloud} {local} {status.llm ? 'Free-form requests are understood by a language model on Groq.' : ''}
    </p>
  )
}

export function ListeningTab() {
  const l = useSettings((s) => s.profile.listening)
  const setListening = useSettings((s) => s.setListening)

  return (
    <TabBody title="Listening" intro="Lector reacts to spoken commands. Everything it hears and does is shown above the player and in the activity list.">
      <Group title="Language">
        <Segmented label="Language you speak commands in" value={l.language} onChange={(language) => setListening({ language })} options={LANGUAGES} />
        <p className="-mt-2 text-[12.5px] text-ink-muted">Each language has its own set of phrases; edit them under Commands. The voice itself reads English.</p>
      </Group>

      <Group title="Microphone">
        <Segmented
          label="How to talk to Lector"
          value={l.mode}
          onChange={(mode) => setListening({ mode })}
          options={[{ value: 'push-to-talk', label: 'Push to talk' }, { value: 'hands-free', label: 'Always listening' }]}
        />
        <p className="-mt-2 text-[12.5px] leading-relaxed text-ink-muted">
          {l.mode === 'push-to-talk'
            ? 'Hold the microphone button or the M key while you speak, or tap it and say one command. Reading pauses while you talk.'
            : 'Commands are heard at any time. While Lector reads aloud it listens more strictly and ignores its own voice.'}
        </p>
        <Slider
          label="Sensitivity"
          value={l.sensitivity}
          min={0}
          max={1}
          step={0.05}
          onChange={(sensitivity) => setListening({ sensitivity })}
          format={(s) => (s < 0.34 ? 'noisy room' : s > 0.66 ? 'quiet room' : 'normal')}
        />
        {l.mode === 'hands-free' && (
          <p className="flex items-start gap-2 rounded-lg bg-accent-soft px-3 py-2 text-[12.5px] leading-relaxed text-accent-soft-ink">
            <Headphones size={15} className="mt-0.5 shrink-0" />
            With loudspeakers the microphone also hears the reading voice. Headphones give the most reliable hands-free control.
          </p>
        )}
      </Group>

      <Group title="Recognition">
        <Segmented
          label="Speech recogniser"
          value={l.engine}
          onChange={(engine) => setListening({ engine })}
          options={[{ value: 'auto', label: 'Automatic' }, { value: 'cloud', label: 'Cloud' }, { value: 'local', label: 'This computer' }]}
        />
        <EngineStatus />
        <Switch
          label="Understand free-form requests"
          description="When a phrase is not in the command list, ask a language model which command was meant (“could you slow down a bit”)."
          checked={l.llm_fallback}
          onChange={(llm_fallback) => setListening({ llm_fallback })}
        />
      </Group>

      <Group title="Feedback">
        <Segmented
          label="Confirm each command with"
          value={l.confirmations}
          onChange={(confirmations) => setListening({ confirmations })}
          options={[{ value: 'sound', label: 'A short sound' }, { value: 'voice', label: 'A spoken reply' }, { value: 'off', label: 'Nothing' }]}
        />
        <Switch
          label="System notifications"
          description="When Lector is in a background tab, show what it heard as a desktop notification."
          checked={l.system_notifications}
          onChange={async (on) => {
            if (on && 'Notification' in window && Notification.permission !== 'granted') {
              const p = await Notification.requestPermission()
              if (p !== 'granted') return
            }
            setListening({ system_notifications: on })
          }}
        />
      </Group>
    </TabBody>
  )
}
