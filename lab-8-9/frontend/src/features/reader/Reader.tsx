import { useQuery } from '@tanstack/react-query'
import { ExternalLink, FilePenLine, Play, TextQuote } from 'lucide-react'
import { useEffect, useMemo, useRef } from 'react'

import { Button, cx, Kbd, Spinner, Tip } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { minutesLabel, plainText } from '@/lib/format'
import { navigate } from '@/lib/router'
import { usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'

import { BlockView } from './BlockView'
import { Contents } from './Contents'
import { SelectionToolbar } from './SelectionToolbar'

function useAutoScroll() {
  const lastUserScroll = useRef(0)
  useEffect(() => {
    const mark = () => (lastUserScroll.current = Date.now())
    window.addEventListener('wheel', mark, { passive: true })
    window.addEventListener('touchmove', mark, { passive: true })
    return () => {
      window.removeEventListener('wheel', mark)
      window.removeEventListener('touchmove', mark)
    }
  }, [])
  useEffect(
    () =>
      usePlayer.subscribe((s, prev) => {
        if (s.snippet || (s.block === prev.block && s.sentence === prev.sentence)) return
        if (s.status !== 'playing' && s.status !== 'loading') return
        if (Date.now() - lastUserScroll.current < 5000) return
        const el = document.querySelector(`[data-b="${s.block}"][data-s="${s.sentence}"]`)
        if (!el) return
        const r = el.getBoundingClientRect()
        const top = 90
        const bottom = window.innerHeight - 180 // keep clear of the player
        if (r.top < top || r.bottom > bottom) {
          const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
          el.scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' })
        }
      }),
    [],
  )
}

export function Reader({ id }: { id: string }) {
  const { data: doc, error, isLoading } = useQuery({ queryKey: ['document', id], queryFn: () => api.document(id) })
  const openDocument = usePlayer((s) => s.openDocument)
  const status = usePlayer((s) => s.status)
  const unit = usePlayer((s) => s.unit)
  const reading = useSettings((s) => s.profile.reading)
  const spokenForm = useUi((s) => s.spokenForm)
  const setSpokenForm = useUi((s) => s.setSpokenForm)
  const container = useRef<HTMLDivElement>(null)
  useAutoScroll()

  useEffect(() => {
    if (doc) openDocument(doc)
  }, [doc, openDocument])

  // Open where the listener stopped last time, or at the top (once per document).
  const docId = doc?.id
  const startBlock = doc?.position?.block ?? 0
  useEffect(() => {
    if (!docId) return
    requestAnimationFrame(() => {
      const el = startBlock > 0 ? document.getElementById(`block-${startBlock}`) : null
      if (el) el.scrollIntoView({ block: 'center' })
      else window.scrollTo({ top: 0 })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId])

  const blocks = doc?.structure.blocks
  const spoken = useQuery({
    queryKey: ['spoken', id, reading],
    enabled: spokenForm && Boolean(blocks),
    queryFn: async () => {
      const texts = blocks!.map((b) => b.text)
      const kinds = blocks!.map((b) => b.kind)
      const [plain, headings] = await Promise.all([
        api.spokenForm(texts, reading, 'text'),
        api.spokenForm(texts, reading, 'heading'),
      ])
      return texts.map((_, i) => (kinds[i] === 'heading' ? headings.spoken[i] : plain.spoken[i]) ?? '')
    },
  })

  const authors = useMemo(() => {
    const a = doc?.authors ?? []
    return a.length > 4 ? `${a.slice(0, 3).join(', ')} and ${a.length - 3} more` : a.join(', ')
  }, [doc])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-8 py-16 text-ink-muted">
        <Spinner /> Opening…
      </div>
    )
  }
  if (error || !doc) {
    return <p className="px-8 py-16 text-danger">{(error as Error | null)?.message ?? 'Document not found.'}</p>
  }

  const started = unit > 0
  const isActive = status === 'playing' || status === 'loading'

  return (
    <div className="flex w-full justify-center">
      <article ref={container} className="relative w-full max-w-[44rem] px-5 pt-10 pb-48 sm:px-8 lg:pt-14" lang="en">
        <header className="mb-12">
          <h1 className="font-serif text-[2.1rem] leading-[1.15] font-semibold tracking-[-0.02em] text-balance text-ink sm:text-[2.4rem]">
            {plainText(doc.title)}
          </h1>
          {authors && <p className="mt-3 text-[15px] leading-relaxed text-ink-muted">{authors}</p>}
          <div className="mt-5 flex flex-wrap items-center gap-2">
            {!isActive && (
              <Button variant="primary" onClick={() => void usePlayer.getState().play(started ? undefined : 0)}>
                <Play size={15} fill="currentColor" /> {started ? 'Continue' : 'Listen'}
              </Button>
            )}
            <Button
              variant="ghost"
              aria-pressed={spokenForm}
              onClick={() => setSpokenForm(!spokenForm)}
              className={cx(spokenForm && 'bg-accent-soft text-accent-soft-ink hover:bg-accent-soft')}
            >
              <TextQuote size={15} /> Spoken form
            </Button>
            <Tip label={<span className="flex items-center gap-1.5">Edit the title and text <Kbd>E</Kbd></span>}>
              <Button variant="ghost" onClick={() => navigate({ name: 'edit', id: doc.id })}>
                <FilePenLine size={15} /> Edit
              </Button>
            </Tip>
            <span className="text-[13px] text-ink-faint">
              {minutesLabel(doc.minutes)} of listening, {doc.word_count.toLocaleString('en')} words
            </span>
            {doc.source.url && (
              <a href={doc.source.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline">
                Source <ExternalLink size={12} />
              </a>
            )}
          </div>
          {spokenForm && (
            <p className="mt-4 max-w-[60ch] rounded-lg bg-sunken px-3 py-2 text-[13px] leading-relaxed text-ink-muted">
              Under each paragraph is the text exactly as the voice says it: formulas in words, citations dropped, units and acronyms expanded.
              {spoken.isFetching && ' Preparing…'}
            </p>
          )}
        </header>
        <div className="prose-paper text-ink">
          {doc.structure.blocks.map((b, i) => (
            <BlockView key={b.id} block={b} index={i} spoken={spokenForm ? spoken.data?.[i] : undefined} />
          ))}
        </div>
        <SelectionToolbar container={container} />
      </article>
      <Contents doc={doc} />
    </div>
  )
}
