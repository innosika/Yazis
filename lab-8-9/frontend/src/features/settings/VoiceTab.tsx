import { Check, Volume2 } from 'lucide-react'
import { useState } from 'react'

import { cx, Slider, Spinner, Switch } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { speedLabel } from '@/lib/format'
import { useVoices } from '@/lib/queries'
import type { VoiceInfo } from '@/lib/types'
import { useSettings } from '@/stores/settings'

import { Group, TabBody } from './SettingsSheet'

const SAMPLE = 'Hello, I will read your papers aloud. Attention scales as O(n^2) in sequence length.'

function describe(v: VoiceInfo): string {
  return `${v.accent === 'us' ? 'American' : 'British'} ${v.gender}`
}

let previewAudio: HTMLAudioElement | null = null

function usePreview() {
  const [playing, setPlaying] = useState<string | null>(null)
  const { voice, reading } = useSettings((s) => s.profile)
  const play = async (id: string, blend: string | null = null, mix = 0) => {
    previewAudio?.pause()
    setPlaying(id)
    try {
      const synth = await api.synthesize({
        text: SAMPLE, kind: 'text', voice: { id, blend, mix }, speed: voice.speed, pitch: voice.pitch,
        options: reading, priority: 'now',
      })
      previewAudio = new Audio(synth.audio_url)
      previewAudio.volume = Math.min(1, voice.volume)
      previewAudio.onended = () => setPlaying(null)
      await previewAudio.play()
    } catch {
      setPlaying(null)
    }
  }
  return { playing, play }
}

function VoiceCard({ v, selected, onSelect, onPreview, previewing }: {
  v: VoiceInfo; selected: boolean; onSelect: () => void; onPreview: () => void; previewing: boolean
}) {
  return (
    <div
      className={cx(
        'group flex items-center gap-3 rounded-xl border p-2.5 transition-colors',
        selected ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:border-line-strong',
      )}
    >
      <button onClick={onSelect} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-pressed={selected}>
        <span className={cx('flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-serif text-[15px] font-semibold', selected ? 'bg-accent text-accent-ink' : 'bg-sunken text-ink')}>
          {selected ? <Check size={16} /> : v.name.slice(0, 1)}
        </span>
        <span className="grid min-w-0">
          <span className="truncate text-[13.5px] font-medium text-ink">{v.name}</span>
          <span className="truncate text-[12px] text-ink-muted">{describe(v)}</span>
        </span>
      </button>
      <button
        onClick={onPreview}
        aria-label={`Preview ${v.name}`}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-line hover:text-ink"
      >
        {previewing ? <Spinner /> : <Volume2 size={16} />}
      </button>
    </div>
  )
}

export function VoiceTab() {
  const { data: voices = [] } = useVoices()
  const v = useSettings((s) => s.profile.voice)
  const setVoice = useSettings((s) => s.setVoice)
  const [showAll, setShowAll] = useState(false)
  const preview = usePreview()
  const list = voices.filter((x) => showAll || x.featured || x.id === v.voice)
  const groups: [string, VoiceInfo[]][] = [
    ['American English', list.filter((x) => x.accent === 'us')],
    ['British English', list.filter((x) => x.accent === 'gb')],
  ]
  const sameAccent = voices.filter((x) => x.accent === voices.find((y) => y.id === v.voice)?.accent && x.id !== v.voice)

  return (
    <TabBody title="Voice" intro="Kokoro, a neural voice that runs on this computer. The voice is heard from the next sentence on.">
      {groups.map(([title, items]) => (
        <Group key={title} title={title}>
          <div className="grid gap-2 sm:grid-cols-2">
            {items.map((x) => (
              <VoiceCard
                key={x.id}
                v={x}
                selected={x.id === v.voice}
                onSelect={() => setVoice({ voice: x.id, blend: v.blend === x.id ? null : v.blend })}
                onPreview={() => void preview.play(x.id)}
                previewing={preview.playing === x.id}
              />
            ))}
          </div>
        </Group>
      ))}
      <button onClick={() => setShowAll(!showAll)} className="-mt-3 justify-self-start text-[13px] text-accent hover:underline">
        {showAll ? 'Show the recommended voices only' : `Show all ${voices.length} voices`}
      </button>

      <Group title="Blend">
        <Switch
          label="Blend with a second voice"
          description="Mixes two speakers into a new one. Both must share an accent."
          checked={Boolean(v.blend)}
          onChange={(on) => setVoice({ blend: on ? sameAccent[0]?.id ?? null : null })}
        />
        {v.blend && (
          <div className="grid gap-4">
            <label className="grid gap-1.5">
              <span className="text-[13px] text-ink">Second voice</span>
              <select
                value={v.blend}
                onChange={(e) => setVoice({ blend: e.target.value })}
                className="h-9 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink"
              >
                {sameAccent.map((x) => (
                  <option key={x.id} value={x.id}>{x.name}, {describe(x)}</option>
                ))}
              </select>
            </label>
            <Slider
              label="Mix"
              value={v.mix}
              min={0.1}
              max={0.9}
              step={0.05}
              onChange={(mix) => setVoice({ mix })}
              format={(m) => `${Math.round((1 - m) * 100)} / ${Math.round(m * 100)}`}
            />
            <button onClick={() => void preview.play(v.voice, v.blend, v.mix)} className="justify-self-start text-[13px] text-accent hover:underline">
              {preview.playing === v.voice ? 'Playing…' : 'Preview the blend'}
            </button>
          </div>
        )}
      </Group>

      <Group title="Delivery">
        <Slider label="Speed" value={v.speed} min={0.5} max={2} step={0.05} onChange={(speed) => setVoice({ speed: Math.round(speed * 100) / 100 })} format={speedLabel} marks={[1]} />
        <Slider
          label="Pitch"
          value={v.pitch}
          min={-4}
          max={4}
          step={0.5}
          onChange={(pitch) => setVoice({ pitch })}
          format={(p) => (p === 0 ? 'natural' : `${p > 0 ? '+' : ''}${p} semitones`)}
          marks={[0]}
        />
        <Slider label="Volume" value={v.volume} min={0} max={1.5} step={0.05} onChange={(volume) => setVoice({ volume })} format={(x) => `${Math.round(x * 100)}%`} marks={[1]} />
      </Group>

      <Group title="Pauses">
        <Slider label="Between sentences" value={v.sentence_pause} min={0} max={1.5} step={0.05} onChange={(sentence_pause) => setVoice({ sentence_pause })} format={(s) => `${s.toFixed(2)} s`} />
        <Slider label="Between paragraphs" value={v.paragraph_pause} min={0} max={3} step={0.1} onChange={(paragraph_pause) => setVoice({ paragraph_pause })} format={(s) => `${s.toFixed(1)} s`} />
      </Group>
    </TabBody>
  )
}
