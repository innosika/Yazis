import { useQueryClient } from '@tanstack/react-query'
import { BookOpenText, Play, SpellCheck2, Volume2 } from 'lucide-react'
import { useEffect, useState, type RefObject } from 'react'

import { Button, inputClass } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { usePlayer } from '@/stores/player'
import { useVoice } from '@/stores/voice'
import { runCommand, showResult } from '@/voice/actions'

interface Sel {
  text: string
  x: number
  y: number
  block: number | null
  sentence: number | null
}

export function SelectionToolbar({ container }: { container: RefObject<HTMLElement | null> }) {
  const [sel, setSel] = useState<Sel | null>(null)
  const [pronounce, setPronounce] = useState<string | null>(null)
  const [sayAs, setSayAs] = useState('')
  const qc = useQueryClient()

  useEffect(() => {
    const onUp = () => {
      window.setTimeout(() => {
        const s = window.getSelection()
        const root = container.current
        if (!s || s.isCollapsed || !root || !s.rangeCount) {
          setSel(null)
          return
        }
        const range = s.getRangeAt(0)
        if (!root.contains(range.commonAncestorContainer)) return
        const text = s.toString().trim()
        if (text.length < 2) return setSel(null)
        const rect = range.getBoundingClientRect()
        const start = (range.startContainer instanceof Element ? range.startContainer : range.startContainer.parentElement)?.closest('[data-b]')
        setSel({
          text,
          x: rect.left + rect.width / 2,
          y: rect.top,
          block: start ? Number((start as HTMLElement).dataset.b) : null,
          sentence: start ? Number((start as HTMLElement).dataset.s) : null,
        })
      }, 10)
    }
    const onDown = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest('[data-selection-toolbar]')) setSel(null)
    }
    document.addEventListener('mouseup', onUp)
    document.addEventListener('keyup', onUp)
    document.addEventListener('mousedown', onDown)
    const onScroll = () => setSel(null)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      document.removeEventListener('mouseup', onUp)
      document.removeEventListener('keyup', onUp)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', onScroll)
    }
  }, [container])

  if (!sel && !pronounce) return null

  const clear = () => {
    window.getSelection()?.removeAllRanges()
    setSel(null)
  }

  if (pronounce) {
    return (
      <div data-selection-toolbar className="fade-in fixed top-1/3 left-1/2 z-40 w-[min(420px,calc(100vw-32px))] -translate-x-1/2 rounded-xl border border-line bg-surface p-4 shadow-float">
        <form
          className="grid gap-3"
          onSubmit={async (e) => {
            e.preventDefault()
            if (!sayAs.trim()) return
            await api.addLexicon(pronounce, sayAs.trim())
            void qc.invalidateQueries({ queryKey: ['lexicon'] })
            useVoice.getState().showHud({ tone: 'success', text: `“${pronounce}” will be said as “${sayAs.trim()}”` })
            setPronounce(null)
            setSayAs('')
          }}
        >
          <p className="text-[13px] text-ink">
            How should <b className="font-semibold">{pronounce}</b> be said?
          </p>
          <input autoFocus value={sayAs} onChange={(e) => setSayAs(e.target.value)} placeholder="Spell it the way it sounds, e.g. koober netties" className={inputClass} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setPronounce(null)}>Cancel</Button>
            <Button type="button" size="sm" disabled={!sayAs.trim()} onClick={() => void usePlayer.getState().readSnippet(sayAs)}>
              <Volume2 size={14} /> Preview
            </Button>
            <Button type="submit" variant="primary" size="sm" disabled={!sayAs.trim()}>Save</Button>
          </div>
        </form>
      </div>
    )
  }

  const s = sel!
  const oneWord = s.text.split(/\s+/).length <= 3 && s.text.length <= 40
  return (
    <div
      data-selection-toolbar
      role="toolbar"
      aria-label="Selection"
      className="fade-in fixed z-40 flex -translate-x-1/2 -translate-y-full items-center gap-0.5 rounded-xl border border-line bg-surface p-1 shadow-float"
      style={{ left: Math.min(Math.max(s.x, 160), window.innerWidth - 160), top: Math.max(s.y - 10, 64) }}
    >
      <Button size="sm" variant="ghost" onClick={() => { void usePlayer.getState().readSnippet(s.text); clear() }}>
        <Volume2 size={14} /> Read selection
      </Button>
      {s.block !== null && (
        <Button size="sm" variant="ghost" onClick={() => { void usePlayer.getState().jumpToSentence(s.block!, s.sentence ?? 0, true); clear() }}>
          <Play size={14} /> Read from here
        </Button>
      )}
      <Button
        size="sm"
        variant="ghost"
        onClick={async () => {
          const term = s.text.slice(0, 120)
          clear()
          showResult(await runCommand('explain', { term }, { wasPlaying: false, source: 'palette' }))
        }}
      >
        <BookOpenText size={14} /> Explain
      </Button>
      {oneWord && (
        <Button size="sm" variant="ghost" onClick={() => { setPronounce(s.text); setSel(null) }}>
          <SpellCheck2 size={14} /> Pronounce as…
        </Button>
      )}
    </div>
  )
}
