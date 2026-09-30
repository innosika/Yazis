/**
 * Player state for React, backed by one ReadingEngine instance.
 *
 * Only coarse state lives in the store (status, current unit/sentence). The current
 * word is painted straight into the DOM with the CSS Custom Highlight API, so the
 * reader does not re-render forty times a second.
 */

import { create } from 'zustand'

import { buildUnits, ReadingEngine, type EngineStatus, type Unit } from '@/audio/engine'
import { api } from '@/lib/api'
import type { DocumentFull, Word } from '@/lib/types'
import { useSettings } from '@/stores/settings'

interface PlayerState {
  status: EngineStatus
  error: string | null
  doc: DocumentFull | null
  units: Unit[]
  unit: number
  block: number
  sentence: number
  snippet: string | null // text being read outside the document (selection, clipboard)
  muted: boolean
  openDocument: (doc: DocumentFull) => void
  /** The same document changed on the server (edited text or a new title). */
  reloadDocument: (doc: DocumentFull) => void
  closeDocument: () => void
  play: (fromUnit?: number) => Promise<void>
  pause: () => Promise<void>
  toggle: () => Promise<void>
  stop: () => void
  jumpToUnit: (index: number, autoplay?: boolean) => Promise<void>
  jumpToSentence: (block: number, sentence: number, autoplay?: boolean) => Promise<void>
  move: (kind: 'sentence' | 'paragraph' | 'section', delta: 1 | -1) => Promise<void>
  readSnippet: (text: string) => Promise<void>
  endSnippet: () => void
  setMuted: (muted: boolean) => void
}

// ------------------------------------------------------------------ word painting

const blockElements = new Map<number, HTMLElement>()

export function registerBlockElement(index: number, el: HTMLElement | null): void {
  if (el) blockElements.set(index, el)
  else blockElements.delete(index)
}

function rangeFor(blockIndex: number, a: number, b: number): Range | null {
  const root = blockElements.get(blockIndex)
  if (!root) return null
  const segments = root.querySelectorAll<HTMLElement>('[data-o]')
  let startSet = false
  const range = document.createRange()
  for (const seg of segments) {
    const o = Number(seg.dataset.o)
    const len = Number(seg.dataset.l)
    const atomic = seg.dataset.atomic === '1'
    if (!startSet && a < o + len) {
      if (atomic || !seg.firstChild) range.setStartBefore(seg)
      else range.setStart(seg.firstChild, Math.max(0, a - o))
      startSet = true
    }
    if (startSet && b <= o + len) {
      if (atomic || !seg.firstChild) range.setEndAfter(seg)
      else range.setEnd(seg.firstChild, Math.max(0, Math.min(len, b - o)))
      return range
    }
  }
  return startSet ? range : null
}

const supportsHighlights = typeof CSS !== 'undefined' && 'highlights' in CSS

function paintWord(unit: Unit, word: Word | null): void {
  if (!supportsHighlights) return
  if (!word) {
    CSS.highlights.delete('lector-word')
    return
  }
  const range = rangeFor(unit.block, unit.start + word.src_start, unit.start + word.src_end)
  if (range) CSS.highlights.set('lector-word', new Highlight(range))
}

// ------------------------------------------------------------------ store

let engine: ReadingEngine | null = null
let snippetBackup: { units: Unit[]; unit: number } | null = null
let saveTimer = 0

function scheduleSave(doc: DocumentFull | null, unit: Unit, total: number): void {
  if (!doc) return
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    void api.savePosition(doc.id, unit.block, unit.sentence, total ? unit.index / total : 0).catch(() => undefined)
  }, 1500)
}

export const usePlayer = create<PlayerState>((set, get) => {
  const settings = useSettings.getState().profile
  engine = new ReadingEngine(
    {
      onStatus: (status, error) => set({ status, error: error ?? null }),
      onUnit: (unit) => {
        set({ unit: unit.index, block: unit.block, sentence: unit.sentence })
        if (!get().snippet) scheduleSave(get().doc, unit, get().units.length)
      },
      onWord: (unit, word) => {
        if (!get().snippet) paintWord(unit, word)
      },
    },
    settings.voice,
    settings.reading,
  )
  // Follow settings changes (voice, speed, pitch, reading rules, volume).
  useSettings.subscribe((s, prev) => {
    if (s.profile.voice !== prev.profile.voice || s.profile.reading !== prev.profile.reading) {
      void engine?.setParams(s.profile.voice, s.profile.reading)
    }
  })

  return {
    status: 'idle',
    error: null,
    doc: null,
    units: [],
    unit: 0,
    block: 0,
    sentence: 0,
    snippet: null,
    muted: false,

    openDocument: (doc) => {
      if (get().doc?.id === doc.id) return
      const units = buildUnits(doc.structure.blocks)
      const pos = doc.position ?? {}
      const start = units.findIndex((u) => u.block === (pos.block ?? 0) && u.sentence === (pos.sentence ?? 0))
      snippetBackup = null
      engine!.load(units, Math.max(0, start))
      set({ doc, units, snippet: null, error: null })
    },
    reloadDocument: (doc) => {
      const current = get().doc
      if (current?.id !== doc.id) return
      const textChanged = JSON.stringify(current.structure) !== JSON.stringify(doc.structure)
      if (!textChanged) {
        set({ doc }) // a rename: keep playing
        return
      }
      const units = buildUnits(doc.structure.blocks)
      const pos = doc.position ?? {}
      const start = units.findIndex((u) => u.block === (pos.block ?? 0) && u.sentence === (pos.sentence ?? 0))
      CSS.highlights?.delete('lector-word')
      engine!.load(units, Math.max(0, start))
      set({ doc, units, snippet: null, error: null })
    },
    closeDocument: () => {
      engine!.load([], 0)
      set({ doc: null, units: [], unit: 0, block: 0, sentence: 0 })
    },
    play: async (fromUnit) => engine!.play(fromUnit),
    pause: async () => engine!.pause(),
    toggle: async () => engine!.toggle(),
    stop: () => engine!.stop(),
    jumpToUnit: async (index, autoplay = false) => {
      if (autoplay && engine!.currentStatus !== 'playing') await engine!.play(index)
      else await engine!.jump(index)
    },
    jumpToSentence: async (block, sentence, autoplay = false) => {
      const target = get().units.find((u) => u.block === block && u.sentence === sentence)
      if (target) await get().jumpToUnit(target.index, autoplay)
    },
    move: async (kind, delta) => {
      const { units, unit } = get()
      const current = units[unit]
      if (!current) return
      let target: Unit | undefined
      if (kind === 'sentence') {
        // the first unit of the next/previous sentence
        const firsts = units.filter((u) => u.firstOfSentence)
        const here = firsts.findIndex((u) => u.block === current.block && u.sentence === current.sentence)
        target = firsts[Math.max(0, here + delta)]
      } else if (kind === 'paragraph') {
        const firsts = units.filter((u) => u.firstOfBlock)
        const here = firsts.findIndex((u) => u.block === current.block)
        target = firsts[Math.max(0, here + delta)]
      } else {
        const sections = get().doc?.structure.sections ?? []
        const blocks = sections.map((s) => s.block)
        const here = blocks.filter((b) => b <= current.block).length - 1
        const blockTarget = blocks[Math.max(0, here + delta)]
        target = units.find((u) => u.block === blockTarget)
      }
      if (target) await get().jumpToUnit(target.index)
    },
    readSnippet: async (text) => {
      const { units: segs } = await api.segment(text)
      const units: Unit[] = segs.map((s, i) => ({
        index: i, block: s.paragraph, sentence: i, start: s.start, end: s.end,
        text: text.slice(s.start, s.end), kind: 'text', firstOfSentence: true,
        firstOfBlock: i === 0 || segs[i - 1]!.paragraph !== s.paragraph, words: text.slice(s.start, s.end).split(/\s+/).length,
      }))
      if (!units.length) return
      if (!get().snippet) snippetBackup = { units: get().units, unit: get().unit }
      CSS.highlights?.delete('lector-word')
      engine!.load(units, 0)
      set({ snippet: text })
      await engine!.play(0)
    },
    endSnippet: () => {
      const backup = snippetBackup
      snippetBackup = null
      set({ snippet: null })
      engine!.load(backup?.units ?? get().units, backup?.unit ?? 0)
    },
    setMuted: (muted) => {
      engine!.setMuted(muted)
      set({ muted })
    },
  }
})

// When a snippet ends, return to the document where the listener was.
usePlayer.subscribe((s, prev) => {
  if (s.snippet && s.status === 'ended' && prev.status !== 'ended') {
    window.setTimeout(() => usePlayer.getState().endSnippet(), 400)
  }
})

export function getEngine(): ReadingEngine {
  return engine!
}

export function remainingWords(state: Pick<PlayerState, 'units' | 'unit'>): number {
  let words = 0
  for (let i = state.unit; i < state.units.length; i++) words += state.units[i]!.words
  return words
}

export function currentSectionTitle(state: Pick<PlayerState, 'doc' | 'block'>): string | null {
  const sections = state.doc?.structure.sections ?? []
  let title: string | null = null
  for (const s of sections) if (s.block <= state.block) title = s.title
  return title
}

