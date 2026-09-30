/**
 * Everything a voice command, the command palette or a keyboard shortcut can do.
 *
 * Handlers are typed as Record<CommandId, Handler> where CommandId comes from the
 * backend's catalog export, so adding a command there without a handler here is a
 * type error. Each handler returns what to tell the user (the HUD line) and, when it
 * makes sense to say it aloud, a short spoken reply.
 */

import { api } from '@/lib/api'
import { speedLabel } from '@/lib/format'
import { navigate } from '@/lib/router'
import { setTheme } from '@/lib/theme'
import type { VoiceInfo } from '@/lib/types'
import { currentSectionTitle, getEngine, remainingWords, usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'
import { useVoice } from '@/stores/voice'

import { COMMANDS, MACRO_ACTIONS } from './catalog.gen'

export type CommandId = (typeof COMMANDS)[number]['id']
export type MacroAction = (typeof MACRO_ACTIONS)[number]

export interface ActionContext {
  wasPlaying: boolean
  source: 'voice' | 'palette' | 'keyboard'
}

export interface ActionResult {
  hud: string
  reply?: string
  /** true when the action decided playback itself (so push-to-talk must not resume) */
  handledPlayback?: boolean
  tone?: 'success' | 'warning' | 'error'
}

type Slots = Record<string, string | number>
type Handler = (slots: Slots, ctx: ActionContext) => ActionResult | Promise<ActionResult>

let voiceList: VoiceInfo[] = []
export function setVoiceList(voices: VoiceInfo[]): void {
  voiceList = voices
}

const player = () => usePlayer.getState()
const settings = () => useSettings.getState()

function resumeIf(ctx: ActionContext): void {
  if (ctx.wasPlaying) void player().play()
}

function setSpeed(speed: number): ActionResult {
  const s = Math.round(Math.min(2, Math.max(0.5, speed)) * 20) / 20
  settings().setVoice({ speed: s })
  return { hud: `Speed ${speedLabel(s)}`, reply: `Speed ${s}` }
}

function setVolume(volume: number): ActionResult {
  const v = Math.round(Math.min(1.5, Math.max(0, volume)) * 20) / 20
  settings().setVoice({ volume: v })
  if (player().muted) player().setMuted(false)
  return { hud: `Volume ${Math.round(v * 100)}%`, reply: `Volume ${Math.round(v * 100)} percent` }
}

function voiceName(id: string): string {
  return voiceList.find((v) => v.id === id)?.name ?? id.split('_')[1] ?? id
}

function switchVoice(id: string): ActionResult {
  settings().setVoice({ voice: id, blend: null })
  const name = voiceName(id)
  return { hud: `Voice: ${name}`, reply: `This is ${name}` }
}

function pickVoice(filter: (v: VoiceInfo) => boolean): ActionResult {
  const current = settings().profile.voice.voice
  const pool = voiceList.filter((v) => v.featured && filter(v))
  if (!pool.length) return { hud: 'No matching voice', tone: 'warning' }
  const idx = pool.findIndex((v) => v.id === current)
  return switchVoice(pool[(idx + 1) % pool.length]!.id)
}

function requireDoc(): ActionResult | null {
  return player().doc ? null : { hud: 'Open a document first', tone: 'warning' }
}

function currentParagraph(): string {
  const { doc, block } = player()
  return doc?.structure.blocks[block]?.text ?? ''
}

function sectionText(): { title: string; text: string } {
  const { doc, block } = player()
  if (!doc) return { title: '', text: '' }
  const sections = doc.structure.sections
  let start = 0
  let end = doc.structure.blocks.length
  let title = doc.title
  for (let i = 0; i < sections.length; i++) {
    if (sections[i]!.block <= block) {
      start = sections[i]!.block
      title = sections[i]!.title
      end = sections[i + 1]?.block ?? doc.structure.blocks.length
    }
  }
  const text = doc.structure.blocks.slice(start, end).map((b) => b.text).join('\n\n')
  return { title, text }
}

async function assist(kind: 'explain' | 'summary', title: string, run: () => Promise<{ text: string }>): Promise<ActionResult> {
  const ui = useUi.getState()
  ui.setAssistant({ kind, title, text: null, error: null })
  try {
    const { text } = await run()
    useUi.getState().setAssistant({ kind, title, text, error: null })
    await player().pause()
    void getEngine().say(text).catch(() => undefined)
    return { hud: kind === 'explain' ? `Explaining ${title}` : 'Summary ready', handledPlayback: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'The assistant is unavailable'
    useUi.getState().setAssistant({ kind, title, text: null, error: message })
    return { hud: message, tone: 'error' }
  }
}

export const handlers: Record<CommandId, Handler> = {
  play: async () => {
    if (requireDoc()) return requireDoc()!
    await player().play()
    return { hud: 'Reading', handledPlayback: true }
  },
  pause: async () => {
    await player().pause()
    return { hud: 'Paused', handledPlayback: true }
  },
  resume: async () => {
    if (requireDoc()) return requireDoc()!
    await player().play()
    return { hud: 'Continuing', handledPlayback: true }
  },
  stop: () => {
    player().stop()
    return { hud: 'Stopped', handledPlayback: true }
  },
  repeat: async () => {
    const { units, unit } = player()
    const current = units[unit]
    if (!current) return requireDoc() ?? { hud: 'Nothing to repeat' }
    const first = units.find((u) => u.block === current.block && u.sentence === current.sentence)
    await player().jumpToUnit(first?.index ?? unit, true)
    return { hud: 'Repeating the sentence', handledPlayback: true }
  },
  start_over: async () => {
    if (requireDoc()) return requireDoc()!
    await player().jumpToUnit(0, true)
    return { hud: 'From the beginning', handledPlayback: true }
  },
  next_sentence: async (_s, ctx) => {
    await player().move('sentence', 1)
    resumeIf(ctx)
    return { hud: 'Next sentence', handledPlayback: true }
  },
  previous_sentence: async (_s, ctx) => {
    await player().move('sentence', -1)
    resumeIf(ctx)
    return { hud: 'Previous sentence', handledPlayback: true }
  },
  next_paragraph: async (_s, ctx) => {
    await player().move('paragraph', 1)
    resumeIf(ctx)
    return { hud: 'Next paragraph', handledPlayback: true }
  },
  previous_paragraph: async (_s, ctx) => {
    await player().move('paragraph', -1)
    resumeIf(ctx)
    return { hud: 'Previous paragraph', handledPlayback: true }
  },
  next_section: async (_s, ctx) => {
    await player().move('section', 1)
    resumeIf(ctx)
    return { hud: currentSectionTitle(player()) ?? 'Next section', handledPlayback: true }
  },
  go_to_section: async (slots, ctx) => {
    const missing = requireDoc()
    if (missing) return missing
    const { doc, units } = player()
    let block: number | undefined
    let title: string | undefined
    if (typeof slots.section_block === 'number') {
      block = slots.section_block
      title = String(slots.section_title ?? '')
    } else if (typeof slots.number === 'number') {
      const n = String(slots.number).replace(/\.0$/, '')
      const sec = doc!.structure.sections.find((s) => s.title.startsWith(`${n} `))
        ?? doc!.structure.sections.filter((s) => s.level === 1)[Math.round(Number(slots.number)) - 1]
      block = sec?.block
      title = sec?.title
    }
    if (block === undefined) return { hud: `There is no section ${slots.number ?? slots.section ?? ''}`, tone: 'warning' }
    const unit = units.find((u) => u.block === block)
    if (unit) await player().jumpToUnit(unit.index, ctx.source === 'voice' || ctx.wasPlaying)
    return { hud: title ?? 'Section', handledPlayback: true }
  },
  read_abstract: async () => {
    const missing = requireDoc()
    if (missing) return missing
    const { doc, units } = player()
    const sec = doc!.structure.sections.find((s) => /abstract/i.test(s.title))
    const unit = units.find((u) => u.block === (sec ? sec.block : 0))
    if (unit) await player().jumpToUnit(unit.index, true)
    return { hud: sec ? 'Abstract' : 'This document has no abstract; reading from the top', handledPlayback: true }
  },
  faster: () => setSpeed(settings().profile.voice.speed + 0.1),
  slower: () => setSpeed(settings().profile.voice.speed - 0.1),
  set_speed: (slots) => {
    const n = Number(slots.number)
    // "speed 120" means percent
    return setSpeed(n > 3 ? n / 100 : n)
  },
  normal_speed: () => setSpeed(1),
  louder: () => setVolume(settings().profile.voice.volume + 0.15),
  quieter: () => setVolume(settings().profile.voice.volume - 0.15),
  mute: () => {
    player().setMuted(true)
    return { hud: 'Muted — reading continues silently' }
  },
  unmute: () => {
    player().setMuted(false)
    return { hud: 'Sound on', reply: 'Sound on' }
  },
  next_voice: () => pickVoice(() => true),
  switch_voice: (slots) => switchVoice(String(slots.voice)),
  male_voice: () => pickVoice((v) => v.gender === 'male'),
  female_voice: () => pickVoice((v) => v.gender === 'female'),
  british_accent: () => pickVoice((v) => v.accent === 'gb'),
  american_accent: () => pickVoice((v) => v.accent === 'us'),
  where_am_i: () => {
    const missing = requireDoc()
    if (missing) return missing
    const p = player()
    const section = currentSectionTitle(p) ?? p.doc!.title
    const pct = Math.round((p.unit / Math.max(1, p.units.length)) * 100)
    return { hud: `${section}, ${pct}% through`, reply: `${section}. ${pct} percent through the paper.` }
  },
  time_left: () => {
    const missing = requireDoc()
    if (missing) return missing
    const words = remainingWords(player())
    const minutes = Math.max(1, Math.round(words / (155 * settings().profile.voice.speed)))
    const text = minutes === 1 ? 'About a minute left' : `About ${minutes} minutes left`
    return { hud: text, reply: text }
  },
  explain: async (slots) => {
    const term = String(slots.term ?? slots.text ?? '').trim()
    if (!term) return { hud: 'Say what to explain, for example “explain attention”', tone: 'warning' }
    const title = player().doc?.title ?? ''
    return assist('explain', term, () => api.explain(term, currentParagraph(), title))
  },
  summarize: async () => {
    const missing = requireDoc()
    if (missing) return missing
    const { title, text } = sectionText()
    if (text.length < 40) return { hud: 'This section is too short to summarize', tone: 'warning' }
    return assist('summary', title, () => api.summarize(text, player().doc!.title, title))
  },
  read_clipboard: async () => {
    let text = ''
    try {
      text = await navigator.clipboard.readText()
    } catch {
      return { hud: 'The browser did not allow reading the clipboard', tone: 'warning' }
    }
    if (!text.trim()) return { hud: 'The clipboard is empty', tone: 'warning' }
    await player().readSnippet(text)
    return { hud: 'Reading the clipboard', handledPlayback: true }
  },
  new_document: () => {
    navigate({ name: 'new' })
    return { hud: 'New document' }
  },
  open_library: () => {
    navigate({ name: 'home' })
    useUi.getState().setLibrary(true)
    return { hud: 'Library' }
  },
  dark_mode: () => {
    setTheme('dark')
    return { hud: 'Dark mode' }
  },
  light_mode: () => {
    setTheme('light')
    return { hud: 'Light mode' }
  },
  show_commands: () => {
    useUi.getState().openSettings('commands')
    return { hud: 'Voice commands', reply: 'Here are the commands' }
  },
  stop_listening: () => {
    window.dispatchEvent(new CustomEvent('lector-mic', { detail: 'off' }))
    return { hud: 'Microphone off' }
  },
}

/** Steps a custom command can chain (the catalog's macro actions). */
const macro: Record<MacroAction, (value: string | number | null, ctx: ActionContext) => ActionResult | Promise<ActionResult>> = {
  ...(Object.fromEntries(
    (Object.keys(handlers) as CommandId[]).map((id) => [id, (_v: unknown, ctx: ActionContext) => handlers[id]({}, ctx)]),
  ) as Record<CommandId, (v: string | number | null, ctx: ActionContext) => ActionResult | Promise<ActionResult>>),
  go_to_section: (v, ctx) => handlers.go_to_section({ number: Number(v) }, ctx),
  set_speed: (v) => setSpeed(Number(v)),
  switch_voice: (v) => switchVoice(String(v)),
  set_volume: (v) => setVolume(Number(v) > 3 ? Number(v) / 100 : Number(v)),
  set_pitch: (v) => {
    const st = Math.max(-4, Math.min(4, Number(v)))
    settings().setVoice({ pitch: st })
    return { hud: `Pitch ${st > 0 ? '+' : ''}${st}` }
  },
  say: (v) => {
    const text = String(v ?? '')
    if (text) void getEngine().say(text).catch(() => undefined)
    return { hud: text }
  },
}

export async function runCommand(
  id: string,
  slots: Slots,
  ctx: ActionContext,
  steps: { action: string; value: string | number | null }[] = [],
): Promise<ActionResult> {
  if (id.startsWith('custom:')) {
    let last: ActionResult = { hud: 'Done' }
    let handledPlayback = false
    for (const step of steps) {
      const fn = macro[step.action as MacroAction]
      if (!fn) continue
      last = await fn(step.value, ctx)
      handledPlayback ||= Boolean(last.handledPlayback)
    }
    return { ...last, handledPlayback }
  }
  const handler = handlers[id as CommandId]
  if (!handler) return { hud: `Unknown command ${id}`, tone: 'error' }
  return handler(slots, ctx)
}

export const COMMAND_META = COMMANDS

export function showResult(result: ActionResult): void {
  useVoice.getState().showHud({ tone: result.tone ?? 'success', text: result.hud })
}
