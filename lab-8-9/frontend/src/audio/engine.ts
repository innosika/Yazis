/**
 * The reading engine: turns a list of playback units into continuous speech.
 *
 * Each unit is synthesized on the server (cached there by content), decoded once, and
 * scheduled on a single AudioContext timeline so consecutive units play back to back
 * with exactly the configured pause between them. Up to three units ahead are fetched
 * while the current one plays. Pausing suspends the context, which freezes the clock,
 * so word timings stay exact across pauses.
 *
 * The engine knows nothing about React; it reports progress through callbacks.
 */

import { api, type SynthesizeParams } from '@/lib/api'
import type { ReadingSettings, Synthesis, VoiceSettings, Word } from '@/lib/types'

export interface Unit {
  index: number
  block: number
  sentence: number
  start: number // offsets into the block text
  end: number
  text: string
  kind: 'text' | 'heading'
  firstOfSentence: boolean
  firstOfBlock: boolean
  words: number
}

export type EngineStatus = 'idle' | 'loading' | 'playing' | 'paused' | 'ended' | 'error'

export interface EngineCallbacks {
  onStatus: (status: EngineStatus, error?: string) => void
  onUnit: (unit: Unit) => void
  onWord: (unit: Unit, word: Word | null) => void
}

interface Prepared {
  synth: Synthesis
  buffer: AudioBuffer
}

interface Scheduled {
  unit: Unit
  prepared: Prepared
  source: AudioBufferSourceNode
  startAt: number // context time at which buffer offset `offset` plays
  offset: number
  endAt: number
}

const PREFETCH = 3
const SCHEDULE_AHEAD = 2

export class ReadingEngine {
  private ctx: AudioContext | null = null
  private gain: GainNode | null = null
  private units: Unit[] = []
  private prepared = new Map<number, Promise<Prepared>>()
  private controllers = new Map<number, AbortController>()
  private scheduled: Scheduled[] = []
  private position = 0 // unit index the listener is at
  private nextToSchedule = 0
  private status: EngineStatus = 'idle'
  private raf = 0
  private pumpTimer = 0
  private generation = 0
  private lastUnit = -1
  private lastWord: Word | null = null
  private voice: VoiceSettings
  private reading: ReadingSettings
  private spokenLog: { text: string; at: number }[] = []
  private volume = 1
  private muted = false
  private ducked = false
  private announcer: AudioContext | null = null
  private announcing: AudioBufferSourceNode | null = null

  constructor(
    private cb: EngineCallbacks,
    voice: VoiceSettings,
    reading: ReadingSettings,
  ) {
    this.voice = voice
    this.reading = reading
  }

  // ------------------------------------------------------------------ public API

  get currentStatus(): EngineStatus {
    return this.status
  }

  get currentIndex(): number {
    return this.position
  }

  get unitList(): Unit[] {
    return this.units
  }

  load(units: Unit[], startAt = 0): void {
    this.hardStop()
    this.units = units
    this.prepared.clear()
    this.position = Math.max(0, Math.min(startAt, units.length - 1))
    this.setStatus('idle')
    if (units[this.position]) this.cb.onUnit(units[this.position]!)
  }

  async play(from?: number, offsetSeconds = 0): Promise<void> {
    if (!this.units.length) return
    const ctx = this.ensureContext()
    if (from !== undefined) this.position = Math.max(0, Math.min(from, this.units.length - 1))
    if (this.status === 'paused' && from === undefined && this.scheduled.length) {
      await ctx.resume()
      this.setStatus('playing')
      return
    }
    this.hardStop()
    const gen = ++this.generation
    this.nextToSchedule = this.position
    // Move the highlight at once; the audio follows when it is ready.
    const target = this.units[this.position]
    if (target && target.index !== this.lastUnit) {
      this.lastUnit = target.index
      this.cb.onUnit(target)
    }
    this.setStatus('loading')
    if (ctx.state === 'suspended') await ctx.resume()
    try {
      await this.scheduleNext(gen, offsetSeconds, 'now')
    } catch (err) {
      if (gen !== this.generation) return
      this.setStatus('error', err instanceof Error ? err.message : 'Could not synthesize speech')
      return
    }
    if (gen !== this.generation) return
    this.setStatus('playing')
    this.startTicking()
    this.pumpTimer = window.setInterval(() => void this.pump(gen), 250)
    void this.pump(gen)
  }

  async pause(): Promise<void> {
    if (this.status !== 'playing' && this.status !== 'loading') return
    if (this.status === 'loading') {
      this.hardStop()
      this.setStatus('paused')
      return
    }
    await this.ctx?.suspend()
    this.setStatus('paused')
  }

  async resume(): Promise<void> {
    if (this.status === 'paused' && this.scheduled.length) {
      await this.ctx?.resume()
      this.setStatus('playing')
    } else {
      await this.play(this.position)
    }
  }

  async toggle(): Promise<void> {
    if (this.status === 'playing' || this.status === 'loading') await this.pause()
    else if (this.status === 'ended') await this.play(0)
    else await this.resume()
  }

  stop(): void {
    this.hardStop()
    this.setStatus('idle')
    const unit = this.units[this.position]
    if (unit) this.cb.onWord(unit, null)
  }

  /** Move to a unit. Keeps playing if it was playing, otherwise just moves. */
  async jump(index: number): Promise<void> {
    const target = Math.max(0, Math.min(index, this.units.length - 1))
    const wasActive = this.status === 'playing' || this.status === 'loading'
    const wasPaused = this.status === 'paused'
    this.position = target
    if (wasActive) {
      await this.play(target)
    } else {
      this.hardStop()
      this.setStatus(wasPaused ? 'paused' : 'idle')
      const unit = this.units[target]
      if (unit) {
        this.lastUnit = unit.index
        this.cb.onUnit(unit)
        this.cb.onWord(unit, null)
      }
    }
  }

  setVolume(volume: number): void {
    this.volume = volume
    this.applyGain()
  }

  setMuted(muted: boolean): void {
    this.muted = muted
    this.applyGain()
  }

  get isMuted(): boolean {
    return this.muted
  }

  /** Barge-in: drop the reading voice to 20% while the listener is speaking, so the
   *  microphone hears them rather than Lector. Fast attack, gentle release. */
  duck(on: boolean): void {
    this.ducked = on
    if (this.gain && this.ctx) {
      const target = this.muted ? 0 : this.volume * (on ? 0.2 : 1)
      this.gain.gain.setTargetAtTime(target, this.ctx.currentTime, on ? 0.015 : 0.12)
    }
  }

  /** New voice, speed or reading options. Upcoming audio is re-requested; if speaking,
   *  the current unit restarts at the word being spoken so the change is heard at once. */
  async setParams(voice: VoiceSettings, reading: ReadingSettings): Promise<void> {
    const changed = signature(voice, reading) !== signature(this.voice, this.reading)
    const pausesChanged = voice.sentence_pause !== this.voice.sentence_pause || voice.paragraph_pause !== this.voice.paragraph_pause
    this.voice = voice
    this.reading = reading
    this.setVolume(voice.volume)
    if (!changed && !pausesChanged) return
    if (changed) {
      for (const c of this.controllers.values()) c.abort()
      this.controllers.clear()
      this.prepared.clear()
    }
    if (this.status === 'playing' || this.status === 'loading') {
      const current = this.currentScheduled()
      const unit = current?.unit.index ?? this.position
      const wordIndex = current ? this.wordIndexAt(current) : 0
      if (changed) {
        const fresh = await this.prepare(unit, 'now').catch(() => null)
        const offset = fresh?.synth.words[wordIndex]?.start ?? 0
        await this.play(unit, Math.max(0, offset - 0.05))
      } else {
        await this.play(unit, current ? this.currentOffset(current) : 0)
      }
    } else if (this.status === 'paused') {
      this.hardStop()
      this.setStatus('paused')
    }
  }

  /** Words heard between two performance.now() timestamps (for echo filtering). */
  spokenBetween(fromMs: number, toMs: number): string {
    return this.spokenLog
      .filter((w) => w.at >= fromMs && w.at <= toMs)
      .map((w) => w.text)
      .join(' ')
  }

  /** Speak a short text in the current voice (confirmations, assistant answers).
   *  Uses its own AudioContext so a paused document stays paused underneath. */
  async say(text: string): Promise<void> {
    this.announcer ??= new AudioContext()
    const ctx = this.announcer
    if (ctx.state === 'suspended') await ctx.resume()
    const synth = await api.synthesize(this.params(text, 'text', 'now'))
    const res = await fetch(synth.audio_url)
    const buffer = await ctx.decodeAudioData(await res.arrayBuffer())
    this.announcing?.stop()
    await new Promise<void>((resolve) => {
      const src = ctx.createBufferSource()
      const gain = ctx.createGain()
      gain.gain.value = this.muted ? 0 : this.volume
      src.buffer = buffer
      src.connect(gain).connect(ctx.destination)
      src.onended = () => resolve()
      this.announcing = src
      src.start()
    })
  }

  stopSaying(): void {
    try {
      this.announcing?.stop()
    } catch {
      /* not playing */
    }
    this.announcing = null
  }

  destroy(): void {
    this.hardStop()
    void this.ctx?.close()
    this.ctx = null
  }

  // ------------------------------------------------------------------ internals

  private ensureContext(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext({ latencyHint: 'playback' })
      this.gain = this.ctx.createGain()
      this.gain.connect(this.ctx.destination)
      this.applyGain()
    }
    return this.ctx
  }

  private applyGain(): void {
    const level = this.muted ? 0 : this.volume * (this.ducked ? 0.2 : 1)
    if (this.gain && this.ctx) this.gain.gain.setTargetAtTime(level, this.ctx.currentTime, 0.02)
  }

  private setStatus(status: EngineStatus, error?: string): void {
    this.status = status
    this.cb.onStatus(status, error)
  }

  private hardStop(): void {
    this.generation++
    window.clearInterval(this.pumpTimer)
    cancelAnimationFrame(this.raf)
    for (const s of this.scheduled) {
      s.source.onended = null
      try {
        s.source.stop()
      } catch {
        /* never started */
      }
      s.source.disconnect()
    }
    this.scheduled = []
    for (const [index, c] of this.controllers) {
      if (index !== this.position) c.abort()
    }
    // A suspended context would keep the next play() silent.
    if (this.ctx?.state === 'suspended' && this.status !== 'paused') void this.ctx.resume()
  }

  private params(text: string, kind: Unit['kind'], priority: SynthesizeParams['priority']): SynthesizeParams {
    return {
      text,
      kind,
      voice: { id: this.voice.voice, blend: this.voice.blend, mix: this.voice.mix },
      speed: this.voice.speed,
      pitch: this.voice.pitch,
      options: this.reading,
      priority,
    }
  }

  private prepare(index: number, priority: SynthesizeParams['priority']): Promise<Prepared> {
    const existing = this.prepared.get(index)
    if (existing) return existing
    const unit = this.units[index]
    if (!unit) return Promise.reject(new Error('no such unit'))
    const controller = new AbortController()
    this.controllers.set(index, controller)
    const promise = (async () => {
      const synth = await api.synthesize(this.params(unit.text, unit.kind, priority), controller.signal)
      const buffer = await this.decode(synth.audio_url, controller.signal)
      return { synth, buffer }
    })()
    promise.catch(() => {
      if (this.prepared.get(index) === promise) this.prepared.delete(index)
    }).finally(() => {
      if (this.controllers.get(index) === controller) this.controllers.delete(index)
    })
    this.prepared.set(index, promise)
    // Keep memory bounded: forget decoded audio well behind the listener.
    for (const key of this.prepared.keys()) {
      if (key < this.position - 2) this.prepared.delete(key)
    }
    return promise
  }

  private async decode(url: string, signal?: AbortSignal): Promise<AudioBuffer> {
    const res = await fetch(url, { signal })
    if (!res.ok) throw new Error('audio unavailable')
    const data = await res.arrayBuffer()
    return this.ensureContext().decodeAudioData(data)
  }

  private gapBefore(unit: Unit): number {
    if (unit.firstOfBlock) return this.voice.paragraph_pause
    if (unit.firstOfSentence) return this.voice.sentence_pause
    return 0.04
  }

  private async scheduleNext(gen: number, offsetSeconds = 0, priority: SynthesizeParams['priority'] = 'prefetch'): Promise<void> {
    const index = this.nextToSchedule
    const unit = this.units[index]
    if (!unit) return
    const prepared = await this.prepare(index, priority)
    if (gen !== this.generation || !this.ctx || !this.gain) return
    const ctx = this.ctx
    const prev = this.scheduled[this.scheduled.length - 1]
    const startAt = prev ? prev.endAt + this.gapBefore(unit) : ctx.currentTime + 0.05
    const source = ctx.createBufferSource()
    source.buffer = prepared.buffer
    source.connect(this.gain)
    const offset = Math.min(offsetSeconds, Math.max(0, prepared.buffer.duration - 0.05))
    source.start(startAt, offset)
    const item: Scheduled = { unit, prepared, source, startAt, offset, endAt: startAt + prepared.buffer.duration - offset }
    source.onended = () => {
      this.scheduled = this.scheduled.filter((s) => s !== item)
      if (gen === this.generation && !this.scheduled.length && this.nextToSchedule >= this.units.length) {
        window.clearInterval(this.pumpTimer)
        cancelAnimationFrame(this.raf)
        this.cb.onWord(unit, null)
        this.setStatus('ended')
      }
    }
    this.scheduled.push(item)
    this.nextToSchedule = index + 1
  }

  private scheduling = false

  private async pump(gen: number): Promise<void> {
    if (this.scheduling || gen !== this.generation || this.status === 'paused') return
    this.scheduling = true
    try {
      // Prefetch a few units ahead of what is scheduled.
      for (let i = this.nextToSchedule; i < Math.min(this.units.length, this.nextToSchedule + PREFETCH); i++) {
        void this.prepare(i, 'prefetch').catch(() => undefined)
      }
      while (
        gen === this.generation &&
        this.nextToSchedule < this.units.length &&
        this.scheduled.filter((s) => s.endAt > (this.ctx?.currentTime ?? 0)).length < SCHEDULE_AHEAD
      ) {
        await this.scheduleNext(gen)
      }
    } catch (err) {
      if (gen === this.generation && !this.scheduled.length) {
        this.setStatus('error', err instanceof Error ? err.message : 'Playback failed')
      }
    } finally {
      this.scheduling = false
    }
  }

  private currentScheduled(): Scheduled | undefined {
    const t = this.ctx?.currentTime ?? 0
    return this.scheduled.find((s) => t < s.endAt) ?? this.scheduled[this.scheduled.length - 1]
  }

  private currentOffset(s: Scheduled): number {
    const t = this.ctx?.currentTime ?? 0
    return Math.max(0, s.offset + (t - s.startAt))
  }

  private wordIndexAt(s: Scheduled): number {
    const at = this.currentOffset(s)
    const words = s.prepared.synth.words
    let idx = 0
    for (let i = 0; i < words.length; i++) {
      if (words[i]!.start <= at) idx = i
      else break
    }
    return idx
  }

  private startTicking(): void {
    cancelAnimationFrame(this.raf)
    const tick = () => {
      this.raf = requestAnimationFrame(tick)
      if (this.status !== 'playing') return
      const s = this.currentScheduled()
      if (!s || !this.ctx) return
      if (this.ctx.currentTime < s.startAt - 0.01) return // in the pause before it
      if (s.unit.index !== this.lastUnit) {
        this.lastUnit = s.unit.index
        this.position = s.unit.index
        this.cb.onUnit(s.unit)
      }
      const at = this.currentOffset(s)
      const word = s.prepared.synth.words.find((w) => at >= w.start - 0.02 && at < w.end + 0.06) ?? null
      if (word !== this.lastWord) {
        this.lastWord = word
        this.cb.onWord(s.unit, word)
        if (word) {
          this.spokenLog.push({ text: word.text, at: performance.now() })
          if (this.spokenLog.length > 200) this.spokenLog.splice(0, 100)
        }
      }
    }
    this.raf = requestAnimationFrame(tick)
  }
}

function signature(v: VoiceSettings, r: ReadingSettings): string {
  return JSON.stringify([v.voice, v.blend, v.blend ? v.mix : 0, v.speed, v.pitch, r])
}

/** Flatten a document into playback units. */
export function buildUnits(
  blocks: { kind: string; text: string; sentences: { start: number; end: number; units: [number, number][] }[] }[],
): Unit[] {
  const units: Unit[] = []
  blocks.forEach((block, b) => {
    block.sentences.forEach((sentence, s) => {
      sentence.units.forEach(([start, end], u) => {
        const text = block.text.slice(start, end)
        units.push({
          index: units.length,
          block: b,
          sentence: s,
          start,
          end,
          text,
          kind: block.kind === 'heading' ? 'heading' : 'text',
          firstOfSentence: u === 0,
          firstOfBlock: s === 0 && u === 0,
          words: text.split(/\s+/).length,
        })
      })
    })
  })
  return units
}
