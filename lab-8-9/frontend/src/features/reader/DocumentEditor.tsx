import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Heading1, List, Sigma, Pilcrow } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { Button, Kbd, Spinner } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { useUpdateDocument } from '@/lib/documents'
import { minutesLabel } from '@/lib/format'
import { navigate, setNavigationGuard, type Route } from '@/lib/router'
import { usePlayer } from '@/stores/player'
import { useVoice } from '@/stores/voice'

interface Draft {
  title: string
  authors: string
  text: string
}

function words(text: string): number {
  const t = text.replace(/^#{1,6}\s+/gm, '').replace(/\\\(.*?\\\)|\$[^$]*\$/g, ' x ').trim()
  return t ? t.split(/\s+/).length : 0
}

function Hint({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-ink-faint">{icon}</span>
      {children}
    </span>
  )
}

/** Grow a textarea with its content so the page, not the box, scrolls. */
function useAutosize(ref: React.RefObject<HTMLTextAreaElement | null>, value: string) {
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight + 2}px`
  }, [ref, value])
}

export function DocumentEditor({ id }: { id: string }) {
  const source = useQuery({ queryKey: ['document-source', id], queryFn: () => api.documentSource(id), gcTime: 0, staleTime: 0 })
  const [draft, setDraft] = useState<Draft | null>(null)
  const [confirmLeave, setConfirmLeave] = useState<Route | null>(null)
  const [error, setError] = useState<string | null>(null)
  const update = useUpdateDocument()
  const titleRef = useRef<HTMLTextAreaElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)

  const original = useMemo<Draft | null>(
    () => (source.data ? { title: source.data.title, authors: source.data.authors.join(', '), text: source.data.text.trimEnd() } : null),
    [source.data],
  )

  useEffect(() => {
    if (original && draft === null) setDraft(original)
  }, [original, draft])

  // Reading the document while its text is being changed would be confusing.
  useEffect(() => {
    const p = usePlayer.getState()
    if (p.doc?.id === id && (p.status === 'playing' || p.status === 'loading')) void p.pause()
  }, [id])

  useAutosize(titleRef, draft?.title ?? '')
  useAutosize(textRef, draft?.text ?? '')

  const dirty = Boolean(draft && original && (draft.title !== original.title || draft.authors !== original.authors || draft.text !== original.text))

  // Hold navigation (library clicks, voice commands) while there are unsaved changes.
  useEffect(() => {
    setNavigationGuard((target) => {
      if (!dirty) return true
      setConfirmLeave(target)
      return false
    })
    return () => setNavigationGuard(null)
  }, [dirty])
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const leave = useCallback(() => navigate({ name: 'doc', id }), [id])

  const save = useCallback(() => {
    if (!draft || !original) return
    if (!dirty) {
      navigate({ name: 'doc', id }, { force: true })
      return
    }
    if (!draft.title.trim()) {
      setError('Give the document a title.')
      titleRef.current?.focus()
      return
    }
    if (!draft.text.trim()) {
      setError('The text is empty. Write something to read, or delete the document from the library.')
      textRef.current?.focus()
      return
    }
    setError(null)
    const patch: { title?: string; authors?: string[]; text?: string } = {}
    if (draft.title !== original.title) patch.title = draft.title
    if (draft.authors !== original.authors) patch.authors = draft.authors.split(',').map((a) => a.trim()).filter(Boolean)
    if (draft.text !== original.text) patch.text = draft.text
    update.mutate(
      { id, patch },
      {
        onSuccess: () => {
          useVoice.getState().showHud({ tone: 'success', text: 'Changes saved' })
          navigate({ name: 'doc', id }, { force: true })
        },
        onError: (e) => setError(e.message),
      },
    )
  }, [draft, original, dirty, id, update])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        save()
      } else if (e.key === 'Escape' && !confirmLeave) {
        e.preventDefault()
        leave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [save, leave, confirmLeave])

  if (source.isLoading || !draft) {
    return (
      <div className="flex items-center gap-2 px-8 py-16 text-ink-muted">
        <Spinner /> Opening the editor…
      </div>
    )
  }
  if (source.error) return <p className="px-8 py-16 text-danger">{(source.error as Error).message}</p>

  const count = words(draft.text)
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch })

  return (
    <div className="flex w-full justify-center">
      <div className="w-full max-w-[44rem] px-5 pb-48 sm:px-8">
        <div className="sticky top-14 z-20 -mx-5 flex min-h-14 flex-wrap items-center gap-2 border-b border-line bg-paper/90 px-5 py-2 backdrop-blur-md sm:-mx-8 sm:px-8">
          {confirmLeave ? (
            <>
              <span className="mr-auto text-[13.5px] text-ink">Leave without saving?</span>
              <Button size="sm" variant="ghost" onClick={() => setConfirmLeave(null)}>Keep editing</Button>
              <Button size="sm" variant="danger" onClick={() => { const t = confirmLeave; setConfirmLeave(null); setNavigationGuard(null); navigate(t, { force: true }) }}>
                Discard changes
              </Button>
            </>
          ) : (
            <>
              <button onClick={leave} aria-label="Back to reading" className="-ml-2 inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-[13px] text-ink-muted hover:bg-sunken hover:text-ink">
                <ArrowLeft size={15} /> <span className="max-sm:hidden">Back to reading</span>
              </button>
              <span className="mr-auto text-[12.5px] text-ink-faint" aria-live="polite">
                {update.isPending ? 'Saving…' : dirty ? 'Unsaved changes' : 'No changes yet'}
              </span>
              <Button size="sm" variant="ghost" onClick={leave} className="max-sm:hidden">Cancel</Button>
              <Button size="sm" variant="primary" onClick={save} disabled={update.isPending}>
                {update.isPending && <Spinner className="h-3.5 w-3.5" />} Save changes
              </Button>
            </>
          )}
        </div>

        {error && <p role="alert" className="mt-4 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">{error}</p>}

        <div className="pt-8">
          <label htmlFor="edit-title" className="text-[12.5px] text-ink-muted">Title</label>
          <textarea
            id="edit-title"
            ref={titleRef}
            rows={1}
            value={draft.title}
            onChange={(e) => set({ title: e.target.value.replace(/\n/g, ' ') })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); textRef.current?.focus() } }}
            placeholder="Title"
            className="mt-1 block w-full resize-none overflow-hidden bg-transparent font-serif text-[2.1rem] leading-[1.15] font-semibold tracking-[-0.02em] text-ink placeholder:text-ink-faint focus:outline-none sm:text-[2.4rem]"
          />
          <label htmlFor="edit-authors" className="mt-5 block text-[12.5px] text-ink-muted">Authors</label>
          <input
            id="edit-authors"
            value={draft.authors}
            onChange={(e) => set({ authors: e.target.value })}
            placeholder="Separate names with commas"
            className="mt-1 block w-full border-b border-line bg-transparent pb-2 text-[15px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
          />
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-sunken px-3 py-2.5 text-[12.5px] text-ink-muted">
          <Hint icon={<Heading1 size={14} />}><code className="text-ink">#</code> or <code className="text-ink">##</code> at the start of a line makes a heading</Hint>
          <Hint icon={<List size={14} />}><code className="text-ink">- </code> makes a list item</Hint>
          <Hint icon={<Sigma size={14} />}><code className="text-ink">$x^2$</code> is a formula</Hint>
          <Hint icon={<Pilcrow size={14} />}>a blank line starts a new paragraph</Hint>
        </div>

        <label htmlFor="edit-text" className="sr-only">Text</label>
        <textarea
          id="edit-text"
          ref={textRef}
          value={draft.text}
          onChange={(e) => set({ text: e.target.value })}
          spellCheck
          className="mt-4 block min-h-[50vh] w-full resize-none overflow-hidden rounded-2xl border border-line bg-surface px-5 py-4 font-serif text-[17px] leading-[1.7] text-ink focus:border-accent focus:outline-none"
        />

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-ink-faint">
          <span className="tabular-nums">{count.toLocaleString('en')} words, about {minutesLabel(count / 155)} of listening</span>
          <span className="flex items-center gap-1.5">
            <Kbd>Ctrl</Kbd><Kbd>S</Kbd> save <span className="mx-1" /> <Kbd>Esc</Kbd> cancel
          </span>
        </div>
      </div>
    </div>
  )
}
