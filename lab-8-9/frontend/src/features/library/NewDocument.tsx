import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardPaste, FileUp, Play } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button, inputClass, Spinner } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { minutesLabel, plainText } from '@/lib/format'
import { useDocuments } from '@/lib/queries'
import { navigate } from '@/lib/router'
import type { DocumentFull } from '@/lib/types'
import { usePlayer } from '@/stores/player'

const EXAMPLES = [
  { id: '1706.03762', title: 'Attention Is All You Need' },
  { id: '2106.09685', title: 'LoRA: Low-Rank Adaptation' },
  { id: '1810.04805', title: 'BERT' },
]

export function NewDocument({ showRecent = false }: { showRecent?: boolean }) {
  const [text, setText] = useState('')
  const [source, setSource] = useState('')
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const { data: docs } = useDocuments()

  const open = (doc: DocumentFull, autoplay: boolean) => {
    void qc.invalidateQueries({ queryKey: ['documents'] })
    qc.setQueryData(['document', doc.id], doc)
    navigate({ name: 'doc', id: doc.id })
    if (autoplay) {
      usePlayer.getState().openDocument(doc)
      void usePlayer.getState().play(0)
    }
  }
  const onError = (e: Error) => setError(e.message)

  const fromText = useMutation({
    mutationFn: ({ autoplay }: { autoplay: boolean }) => api.createFromText(text).then((d) => ({ d, autoplay })),
    onSuccess: ({ d, autoplay }) => open(d, autoplay),
    onError,
  })
  const fromSource = useMutation({ mutationFn: (s: string) => api.importSource(s), onSuccess: (d) => open(d, false), onError })
  const fromFile = useMutation({ mutationFn: (f: File) => api.upload(f), onSuccess: (d) => open(d, false), onError })
  const busy = fromText.isPending || fromSource.isPending || fromFile.isPending

  const paste = async () => {
    setError(null)
    try {
      const clip = await navigator.clipboard.readText()
      if (clip.trim()) setText((t) => (t ? `${t}\n\n${clip}` : clip))
      else setError('The clipboard is empty.')
    } catch {
      setError('The browser did not allow reading the clipboard. Press Ctrl+V in the text box instead.')
    }
  }

  const recent = showRecent ? docs?.[0] : undefined
  const words = text.trim() ? text.trim().split(/\s+/).length : 0

  return (
    <div className="mx-auto w-full max-w-[720px] px-5 pt-10 pb-40 sm:pt-16">
      {recent && (
        <button
          onClick={() => navigate({ name: 'doc', id: recent.id })}
          className="mb-12 grid w-full gap-1 rounded-xl border border-line bg-surface p-4 text-left transition-colors hover:border-line-strong"
        >
          <span className="text-[12.5px] text-ink-muted">
            {recent.progress > 0.01 ? `Continue where you stopped, ${Math.round(recent.progress * 100)}% read` : 'Continue reading'}
          </span>
          <span className="font-serif text-lg leading-snug text-ink">{plainText(recent.title)}</span>
        </button>
      )}

      <h1 className="font-serif text-[2rem] leading-tight font-semibold tracking-[-0.015em] text-ink">What should I read to you?</h1>
      <p className="mt-2 max-w-[56ch] text-[15px] leading-relaxed text-ink-muted">
        Paste an abstract, a paragraph or a whole paper. Formulas, citations, units and acronyms are read the way a person would say them.
      </p>

      <div className="mt-8 overflow-hidden rounded-2xl border border-line bg-surface focus-within:border-accent">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste text here…"
          rows={9}
          className="block w-full resize-y bg-transparent px-5 py-4 font-serif text-[17px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2.5">
          <Button size="sm" variant="ghost" onClick={paste}><ClipboardPaste size={15} /> Paste</Button>
          <Button size="sm" variant="ghost" onClick={() => fileRef.current?.click()}>
            <FileUp size={15} /> Upload PDF or text
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) { setError(null); fromFile.mutate(f) }
              e.target.value = ''
            }}
          />
          <span className="ml-auto text-[12px] text-ink-faint tabular-nums">
            {words ? `${words} words, about ${minutesLabel(words / 155)}` : ''}
          </span>
          <Button size="sm" disabled={!words || busy} onClick={() => fromText.mutate({ autoplay: false })}>Save to library</Button>
          <Button size="sm" variant="primary" disabled={!words || busy} onClick={() => fromText.mutate({ autoplay: true })}>
            <Play size={14} fill="currentColor" /> Read aloud
          </Button>
        </div>
      </div>

      <form
        className="mt-8 grid gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (source.trim()) { setError(null); fromSource.mutate(source.trim()) }
        }}
      >
        <label htmlFor="src" className="text-[13px] text-ink">Or import a paper by arXiv ID or link</label>
        <div className="flex gap-2">
          <input
            id="src"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="1706.03762, arxiv.org/abs/…, or any article URL"
            className={inputClass}
          />
          <Button type="submit" disabled={!source.trim() || busy}>Import</Button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[12.5px] text-ink-muted">
          <span>Try</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex.id}
              type="button"
              disabled={busy}
              onClick={() => { setSource(ex.id); setError(null); fromSource.mutate(ex.id) }}
              className="rounded-full border border-line px-2.5 py-0.5 text-ink hover:border-accent hover:text-accent"
            >
              {ex.title}
            </button>
          ))}
        </div>
      </form>

      <div aria-live="polite" className="mt-6 min-h-6 text-[13px]">
        {busy && (
          <span className="flex items-center gap-2 text-ink-muted">
            <Spinner /> {fromSource.isPending ? 'Fetching the paper and laying it out…' : fromFile.isPending ? 'Reading the file…' : 'Preparing…'}
          </span>
        )}
        {error && !busy && <span className="text-danger">{error}</span>}
      </div>
    </div>
  )
}
