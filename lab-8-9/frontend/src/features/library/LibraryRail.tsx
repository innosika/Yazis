import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Dialog as RDialog } from 'radix-ui'
import { FilePenLine, FileText, Link2, MoreHorizontal, Pencil, Plus, Sparkles, Trash2, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button, cx, IconButton, Menu, Spinner } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { minutesLabel, plainText } from '@/lib/format'
import { useDocuments } from '@/lib/queries'
import { useUpdateDocument } from '@/lib/documents'
import { currentRoute, navigate, useRoute } from '@/lib/router'
import type { DocumentSummary } from '@/lib/types'
import { usePlayer } from '@/stores/player'
import { useVoice } from '@/stores/voice'
import { useUi } from '@/stores/ui'

function SourceIcon({ doc }: { doc: DocumentSummary }) {
  const kind = doc.source.kind
  if (kind === 'sample') return <Sparkles size={14} />
  if (kind === 'arxiv' || kind === 'web') return <Link2 size={14} />
  return <FileText size={14} />
}

function sourceLabel(doc: DocumentSummary): string {
  switch (doc.source.kind) {
    case 'arxiv':
      return `arXiv ${doc.source.id}`
    case 'pdf':
      return 'PDF'
    case 'web':
      return 'Web page'
    case 'sample':
      return 'Built-in example'
    case 'file':
      return 'Text file'
    default:
      return 'Pasted text'
  }
}

function RenameField({ doc, onDone }: { doc: DocumentSummary; onDone: () => void }) {
  const [value, setValue] = useState(doc.title)
  const update = useUpdateDocument()
  const done = useRef(false)
  const save = () => {
    if (done.current) return
    const title = value.trim()
    if (!title || title === doc.title) {
      done.current = true
      onDone()
      return
    }
    done.current = true
    update.mutate({ id: doc.id, patch: { title } }, {
      onSuccess: () => useVoice.getState().showHud({ tone: 'success', text: 'Renamed', detail: title }),
      onError: (e) => useVoice.getState().showHud({ tone: 'error', text: e.message }),
      onSettled: onDone,
    })
  }
  return (
    <div className="rounded-lg bg-surface px-2 py-2 ring-1 ring-accent">
      <label className="sr-only" htmlFor={`rename-${doc.id}`}>Document title</label>
      <textarea
        id={`rename-${doc.id}`}
        autoFocus
        rows={2}
        value={value}
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => setValue(e.target.value.replace(/\n/g, ' '))}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); save() }
          if (e.key === 'Escape') { e.preventDefault(); done.current = true; onDone() }
        }}
        onBlur={save}
        className="block w-full resize-none bg-transparent px-1 font-serif text-[14.5px] leading-snug text-ink focus:outline-none"
      />
      <p className="flex items-center gap-1.5 px-1 pt-1 text-[11.5px] text-ink-faint">
        {update.isPending ? <><Spinner className="h-3 w-3" /> Saving…</> : 'Enter to save, Esc to cancel'}
      </p>
    </div>
  )
}

function Item({ doc, active, onOpen }: { doc: DocumentSummary; active: boolean; onOpen: () => void }) {
  const [mode, setMode] = useState<'view' | 'rename' | 'delete'>('view')
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => api.deleteDocument(doc.id),
    onSuccess: () => {
      if (usePlayer.getState().doc?.id === doc.id) usePlayer.getState().closeDocument()
      const route = currentRoute()
      if ((route.name === 'doc' || route.name === 'edit') && route.id === doc.id) navigate({ name: 'home' }, { force: true })
      void qc.invalidateQueries({ queryKey: ['documents'] })
      useVoice.getState().showHud({ tone: 'success', text: 'Deleted', detail: plainText(doc.title) })
    },
  })
  if (mode === 'rename') {
    return (
      <li>
        <RenameField doc={doc} onDone={() => setMode('view')} />
      </li>
    )
  }
  return (
    <li className="group relative">
      <button
        onClick={onOpen}
        className={cx(
          'grid w-full gap-1 rounded-lg py-2.5 pr-9 pl-3 text-left transition-colors',
          active ? 'bg-accent-soft' : 'hover:bg-sunken',
        )}
      >
        <span className={cx('line-clamp-2 font-serif text-[14.5px] leading-snug', active ? 'text-accent-soft-ink' : 'text-ink')}>
          {plainText(doc.title)}
        </span>
        <span className="flex items-center gap-1.5 text-[12px] text-ink-faint">
          <SourceIcon doc={doc} />
          <span>{sourceLabel(doc)}, {minutesLabel(doc.minutes)}</span>
        </span>
        {doc.progress > 0.01 && (
          <span className="mt-0.5 h-0.5 w-full overflow-hidden rounded-full bg-line" aria-label={`${Math.round(doc.progress * 100)}% read`}>
            <span className="block h-full bg-accent" style={{ width: `${Math.max(3, doc.progress * 100)}%` }} />
          </span>
        )}
      </button>
      {mode === 'delete' ? (
        <div className="absolute inset-0 flex items-center justify-end gap-1 rounded-lg bg-surface/95 px-2 ring-1 ring-danger/30">
          <span className="mr-auto pl-1 text-[12.5px] text-ink">Delete this document?</span>
          <Button size="sm" variant="ghost" onClick={() => setMode('view')}>Keep</Button>
          <Button size="sm" variant="danger" onClick={() => remove.mutate()} disabled={remove.isPending}>Delete</Button>
        </div>
      ) : (
        <Menu
          label={`Actions for ${plainText(doc.title)}`}
          items={[
            { label: 'Rename', icon: <Pencil size={15} />, onSelect: () => setMode('rename') },
            { label: 'Edit text', icon: <FilePenLine size={15} />, onSelect: () => { useUi.getState().setLibrary(false); navigate({ name: 'edit', id: doc.id }) } },
            { label: 'Delete', icon: <Trash2 size={15} />, danger: true, onSelect: () => setMode('delete') },
          ]}
          trigger={
            <button
              className={cx(
                'absolute top-2 right-1.5 flex h-7 w-7 items-center justify-center rounded-md text-ink-muted transition-opacity',
                'opacity-0 group-hover:opacity-100 hover:bg-line hover:text-ink focus-visible:opacity-100 data-[state=open]:bg-line data-[state=open]:opacity-100 max-lg:opacity-100',
              )}
            >
              <MoreHorizontal size={16} />
            </button>
          }
        />
      )}
    </li>
  )
}

function RailContent({ onNavigate, inSheet = false }: { onNavigate?: () => void; inSheet?: boolean }) {
  const { data: docs, isLoading, error } = useDocuments()
  const route = useRoute()
  return (
    <div className="flex h-full flex-col">
      <div className={cx('flex items-center justify-between gap-2 px-4 pt-4 pb-2', inSheet && 'pr-14')}>
        <h2 className="text-[13px] font-semibold text-ink">Library</h2>
        <Button size="sm" variant="primary" onClick={() => { navigate({ name: 'new' }); onNavigate?.() }}>
          <Plus size={15} /> New
        </Button>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-6">
        {isLoading && <p className="px-3 py-2 text-[13px] text-ink-faint">Loading…</p>}
        {error && <p className="px-3 py-2 text-[13px] text-danger">{(error as Error).message}</p>}
        {docs && docs.length === 0 && (
          <p className="px-3 py-2 text-[13px] leading-relaxed text-ink-muted">Nothing here yet. Paste some text or import a paper to start listening.</p>
        )}
        <ul className="grid gap-0.5">
          {docs?.map((d) => (
            <Item
              key={d.id}
              doc={d}
              active={(route.name === 'doc' || route.name === 'edit') && route.id === d.id}
              onOpen={() => { navigate({ name: 'doc', id: d.id }); onNavigate?.() }}
            />
          ))}
        </ul>
      </div>
    </div>
  )
}

export function LibraryRail() {
  const { libraryOpen, setLibrary } = useUi()
  return (
    <>
      <aside className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-[272px] shrink-0 border-r border-line lg:block">
        <RailContent />
      </aside>
      <RDialog.Root open={libraryOpen} onOpenChange={setLibrary}>
        <RDialog.Portal>
          <RDialog.Overlay className="fade-in fixed inset-0 z-40 bg-ink/20 lg:hidden" />
          <RDialog.Content aria-describedby={undefined} className="fade-in fixed inset-y-0 left-0 z-50 w-[300px] max-w-[88vw] border-r border-line bg-paper shadow-float lg:hidden">
            <RDialog.Title className="sr-only">Library</RDialog.Title>
            <div className="absolute top-3 right-3">
              <RDialog.Close asChild>
                <IconButton label="Close library"><X size={18} /></IconButton>
              </RDialog.Close>
            </div>
            <RailContent inSheet onNavigate={() => setLibrary(false)} />
          </RDialog.Content>
        </RDialog.Portal>
      </RDialog.Root>
    </>
  )
}
