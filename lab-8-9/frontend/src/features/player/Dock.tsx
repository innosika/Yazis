import { Pause, Play, SkipBack, SkipForward, Square, Volume1, Volume2, VolumeX } from 'lucide-react'

import { cx, IconButton, Popover, Slider, Spinner, Tip } from '@/components/ui/primitives'
import { minutesLabel, speedLabel } from '@/lib/format'
import { useVoices } from '@/lib/queries'
import { currentSectionTitle, remainingWords, usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'

import { MicControl } from '../voice/MicControl'
import { VoiceHud } from '../voice/VoiceHud'

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2]

function SpeedControl() {
  const speed = useSettings((s) => s.profile.voice.speed)
  const setVoice = useSettings((s) => s.setVoice)
  return (
    <Popover
      className="w-64"
      trigger={
        <button aria-label={`Speed ${speedLabel(speed)}`} className="h-9 min-w-12 rounded-full px-2.5 text-[13px] font-medium text-ink tabular-nums hover:bg-sunken">
          {speedLabel(speed)}
        </button>
      }
    >
      <Slider label="Speed" value={speed} min={0.5} max={2} step={0.05} onChange={(v) => setVoice({ speed: Math.round(v * 100) / 100 })} format={speedLabel} marks={[1]} />
      <div className="mt-3 flex flex-wrap gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => setVoice({ speed: s })}
            className={cx('rounded-full px-2.5 py-1 text-[12.5px] tabular-nums', Math.abs(s - speed) < 0.01 ? 'bg-accent text-accent-ink' : 'bg-sunken text-ink hover:bg-line')}
          >
            {speedLabel(s)}
          </button>
        ))}
      </div>
      <p className="mt-3 text-[12px] text-ink-muted">Say “faster”, “slower” or “speed one point five”.</p>
    </Popover>
  )
}

function VolumeControl() {
  const volume = useSettings((s) => s.profile.voice.volume)
  const setVoice = useSettings((s) => s.setVoice)
  const muted = usePlayer((s) => s.muted)
  const setMuted = usePlayer((s) => s.setMuted)
  const Icon = muted || volume === 0 ? VolumeX : volume < 0.6 ? Volume1 : Volume2
  return (
    <Popover
      className="w-60"
      trigger={
        <button aria-label="Volume" className="hidden h-9 w-9 items-center justify-center rounded-full text-ink-muted hover:bg-sunken hover:text-ink sm:inline-flex">
          <Icon size={18} />
        </button>
      }
    >
      <Slider label="Volume" value={volume} min={0} max={1.5} step={0.05} onChange={(v) => { setVoice({ volume: v }); if (muted) setMuted(false) }} format={(v) => `${Math.round(v * 100)}%`} marks={[1]} />
      <button onClick={() => setMuted(!muted)} className="mt-3 text-[12.5px] text-accent hover:underline">
        {muted ? 'Unmute' : 'Mute'}
      </button>
    </Popover>
  )
}

function VoiceChip() {
  const voiceId = useSettings((s) => s.profile.voice.voice)
  const blend = useSettings((s) => s.profile.voice.blend)
  const { data: voices } = useVoices()
  const voice = voices?.find((v) => v.id === voiceId)
  const other = voices?.find((v) => v.id === blend)
  const openSettings = useUi((s) => s.openSettings)
  const name = voice ? (other ? `${voice.name} + ${other.name}` : voice.name) : voiceId
  return (
    <Tip label="Voice settings">
      <button onClick={() => openSettings('voice')} className="hidden h-9 max-w-40 items-center gap-2 rounded-full pr-3 pl-1 hover:bg-sunken md:flex">
        <span aria-hidden className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft font-serif text-[13px] font-semibold text-accent-soft-ink">
          {name.slice(0, 1)}
        </span>
        <span className="truncate text-[13px] text-ink">{name}</span>
      </button>
    </Tip>
  )
}

function Progress() {
  const units = usePlayer((s) => s.units)
  const unit = usePlayer((s) => s.unit)
  const doc = usePlayer((s) => s.doc)
  const block = usePlayer((s) => s.block)
  const snippet = usePlayer((s) => s.snippet)
  const speed = useSettings((s) => s.profile.voice.speed)
  if (snippet) {
    return (
      <div className="min-w-0 flex-1 px-2">
        <p className="truncate text-[13px] text-ink">Reading the selected text</p>
        <p className="truncate text-[12px] text-ink-muted">Stop to return to where you were</p>
      </div>
    )
  }
  if (!doc) {
    return (
      <div className="min-w-0 flex-1 px-2">
        <p className="truncate text-[13px] text-ink-muted">Open a document to start listening</p>
      </div>
    )
  }
  const fraction = units.length > 1 ? unit / (units.length - 1) : 0
  const left = remainingWords({ units, unit }) / (155 * speed)
  const section = currentSectionTitle({ doc, block })
  const total = doc.structure.blocks.length
  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const target = Math.round(((e.clientX - r.left) / r.width) * (units.length - 1))
    void usePlayer.getState().jumpToUnit(target)
  }
  return (
    <div className="min-w-0 flex-1 px-2">
      <div className="flex items-baseline justify-between gap-3">
        <p className="truncate text-[13px] text-ink">{section ?? doc.title}</p>
        <p className="shrink-0 text-[12px] text-ink-faint tabular-nums">{left < 0.5 ? 'almost done' : `${minutesLabel(left)} left`}</p>
      </div>
      <div
        role="slider"
        tabIndex={0}
        aria-label="Position in document"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fraction * 100)}
        onClick={seek}
        onKeyDown={(e) => {
          if (e.key === 'ArrowRight') void usePlayer.getState().move('paragraph', 1)
          if (e.key === 'ArrowLeft') void usePlayer.getState().move('paragraph', -1)
        }}
        className="group relative mt-1.5 h-3 cursor-pointer"
      >
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-line" />
        <div className="absolute top-1/2 left-0 h-1 -translate-y-1/2 rounded-full bg-accent" style={{ width: `${fraction * 100}%` }} />
        {doc.structure.sections.map((s) => (
          <span key={s.block} className="absolute top-1/2 h-2 w-px -translate-y-1/2 bg-line-strong" style={{ left: `${(s.block / Math.max(1, total)) * 100}%` }} />
        ))}
        <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface opacity-0 transition-opacity group-hover:opacity-100" style={{ left: `${fraction * 100}%` }} />
      </div>
    </div>
  )
}

export function Dock() {
  const status = usePlayer((s) => s.status)
  const error = usePlayer((s) => s.error)
  const doc = usePlayer((s) => s.doc)
  const snippet = usePlayer((s) => s.snippet)
  const p = usePlayer.getState
  const active = status === 'playing' || status === 'loading'
  const canPlay = Boolean(doc) || Boolean(snippet)

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex flex-col items-center px-3 pb-[max(12px,env(safe-area-inset-bottom))]">
      <VoiceHud />
      {error && status === 'error' && (
        <p role="alert" className="pointer-events-auto mb-2 rounded-lg bg-danger-soft px-3 py-1.5 text-[13px] text-danger">{error}</p>
      )}
      <div className="pointer-events-auto flex h-16 w-full max-w-[820px] items-center gap-1 rounded-full border border-line bg-surface/95 pr-2 pl-2 shadow-float backdrop-blur-md sm:gap-1.5">
        <VoiceChip />
        <IconButton label="Previous sentence" disabled={!canPlay} onClick={() => void p().move('sentence', -1)} className="max-sm:hidden">
          <SkipBack size={18} />
        </IconButton>
        <button
          aria-label={active ? 'Pause' : 'Play'}
          disabled={!canPlay}
          onClick={() => void p().toggle()}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent text-accent-ink transition-colors hover:bg-accent-hover disabled:opacity-40"
        >
          {status === 'loading' ? <Spinner className="h-5 w-5" /> : active ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" className="translate-x-px" />}
        </button>
        <IconButton label="Next sentence" disabled={!canPlay} onClick={() => void p().move('sentence', 1)}>
          <SkipForward size={18} />
        </IconButton>
        {snippet && (
          <IconButton label="Stop reading the selection" onClick={() => { p().stop(); p().endSnippet() }}>
            <Square size={16} />
          </IconButton>
        )}
        <Progress />
        <SpeedControl />
        <VolumeControl />
        <MicControl />
      </div>
    </div>
  )
}
