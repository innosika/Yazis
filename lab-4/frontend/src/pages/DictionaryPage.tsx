import { useState } from 'react'

import { EntryCard } from '@/components/dictionary/EntryCard'
import { OovQueue } from '@/components/dictionary/OovQueue'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Hint,
  InlineError,
  Select,
  Skeleton,
  Tabs,
  TextInput,
} from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { DOMAIN_TITLES, thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { useAction, useAsync } from '@/lib/useAsync'
import type { Entry, EntryPage as EntryPageData } from '@/lib/types'

type Tab = 'browse' | 'queue' | 'locks'

const POS_OPTIONS = [
  ['', 'Any part of speech'],
  ['n', 'noun'],
  ['v', 'verb'],
  ['adj', 'adjective'],
  ['adv', 'adverb'],
  ['pn', 'proper noun'],
  ['preposition', 'preposition'],
  ['conjunction', 'conjunction'],
  ['pronoun', 'pronoun'],
  ['numeral', 'numeral'],
  ['interjection', 'interjection'],
  ['phraseologicalUnit', 'phraseological unit'],
  ['proverb', 'proverb'],
] as const

export function DictionaryPage() {
  const { meta, reload: reloadMeta } = useMeta()
  const [tab, setTab] = useState<Tab>('browse')
  const [query, setQuery] = useState('')
  const [pos, setPos] = useState('')
  const [onlyUser, setOnlyUser] = useState(false)
  const [page, setPage] = useState(1)

  const entries = useAsync<EntryPageData>(
    () => api.dictionary.search({ q: query, pos, only_user: onlyUser, page }),
    [query, pos, onlyUser, page],
  )
  const locks = useAsync(() => api.dictionary.overrides(), [])
  const creating = useAction()
  const unlocking = useAction()
  const [showNew, setShowNew] = useState(false)

  const stats = meta?.dictionary

  const replaceEntry = (updated: Entry) => {
    if (!entries.data) return
    entries.setData({
      ...entries.data,
      items: entries.data.items.map((item) => (item.id === updated.id ? updated : item)),
    })
    reloadMeta()
  }

  const removeEntry = (id: number) => {
    if (!entries.data) return
    entries.setData({
      ...entries.data,
      total: Math.max(0, entries.data.total - 1),
      items: entries.data.items.filter((item) => item.id !== id),
    })
    reloadMeta()
  }

  const pages = entries.data ? Math.max(1, Math.ceil(entries.data.total / entries.data.per_page)) : 1

  return (
    <div className="space-y-4">
      {stats && (
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
          {[
            ['Headwords', thousands(stats.entries), 'English entries, one per part of speech'],
            ['Senses', thousands(stats.senses), 'Distinct meanings across all entries'],
            ['Equivalents', thousands(stats.translations), 'Russian words the senses map to'],
            ['Multiword units', thousands(stats.multiword_units), '“machine learning”, “point of view”'],
            ['Your entries', thousands(stats.user_entries), 'Added or corrected by you'],
            ['Your equivalents', thousands(stats.user_translations), 'Russian forms you supplied'],
          ].map(([label, value, hint]) => (
            <div key={label} className="bg-surface px-3.5 py-3">
              <dt className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-ink-faint uppercase">
                {label}
                <Hint text={hint} />
              </dt>
              <dd className="nums mt-1 text-[22px] leading-7 font-semibold tracking-tight text-ink">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-2 pr-4">
          <Tabs
            tabs={[
              { value: 'browse' as Tab, label: 'Browse and correct' },
              { value: 'queue' as Tab, label: 'Replenishment queue' },
              { value: 'locks' as Tab, label: 'Locked senses', count: locks.data?.length },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>

        {tab === 'browse' && (
          <>
            <div className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3">
              <Field label="Search" htmlFor="dict-search">
                <TextInput
                  id="dict-search"
                  type="search"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value)
                    setPage(1)
                  }}
                  placeholder="English headword…"
                  className="min-w-56"
                />
              </Field>
              <Field label="Part of speech" htmlFor="dict-pos">
                <Select
                  id="dict-pos"
                  value={pos}
                  onChange={(event) => {
                    setPos(event.target.value)
                    setPage(1)
                  }}
                  className="min-w-44"
                >
                  {POS_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button
                variant={onlyUser ? 'primary' : 'secondary'}
                onClick={() => {
                  setOnlyUser((value) => !value)
                  setPage(1)
                }}
              >
                Only my edits
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowNew((value) => !value)}
                aria-expanded={showNew}
                className="ml-auto"
              >
                New entry
              </Button>
            </div>

            {showNew && (
              <NewEntryForm
                busy={creating.busy}
                error={creating.error}
                onDismissError={creating.clearError}
                onSubmit={async (headword, entryPos, gloss, forms) => {
                  const created = await creating.run(() =>
                    api.dictionary.create({
                      headword,
                      pos: entryPos,
                      senses: [{ gloss, labels: [], translations: forms }],
                    }),
                  )
                  if (created) {
                    setShowNew(false)
                    setQuery(created.headword)
                    setPage(1)
                    entries.reload()
                    reloadMeta()
                  }
                }}
                onCancel={() => setShowNew(false)}
              />
            )}

            {entries.loading && <Skeleton rows={5} />}
            {entries.error && (
              <div className="p-4">
                <InlineError message={entries.error} />
              </div>
            )}

            {entries.data && entries.data.items.length === 0 && (
              <EmptyState
                title={query ? `Nothing matches “${query}”` : 'No entries'}
                body={
                  query
                    ? 'Try a different spelling, or create the entry with the “New entry” button above.'
                    : 'Type a word to search the dictionary.'
                }
              />
            )}

            {entries.data && entries.data.items.length > 0 && (
              <>
                <div>
                  {entries.data.items.map((entry) => (
                    <EntryCard
                      key={entry.id}
                      entry={entry}
                      onChanged={replaceEntry}
                      onDeleted={removeEntry}
                    />
                  ))}
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5">
                  <span className="nums text-xs text-ink-faint">
                    {thousands(entries.data.total)} matching entries · page {page} of{' '}
                    {thousands(pages)}
                  </span>
                  <span className="flex gap-1.5">
                    <Button
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage((value) => value - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      disabled={page >= pages}
                      onClick={() => setPage((value) => value + 1)}
                    >
                      Next
                    </Button>
                  </span>
                </div>
              </>
            )}
          </>
        )}

        {tab === 'queue' && (
          <OovQueue
            onEntryCreated={() => {
              entries.reload()
              reloadMeta()
            }}
          />
        )}

        {tab === 'locks' && (
          <>
            <p className="border-b border-line bg-raised px-4 py-2.5 text-xs leading-relaxed text-ink-muted">
              A locked sense is the permanent choice for one word in one subject area — it beats
              every disambiguation signal. Locks are created from the <em>Senses</em> tab after a
              translation.
            </p>
            {unlocking.error && (
              <div className="p-3">
                <InlineError message={unlocking.error} onDismiss={unlocking.clearError} />
              </div>
            )}
            {locks.loading && <Skeleton rows={3} />}
            {locks.data && locks.data.length === 0 && (
              <EmptyState
                title="No locked senses"
                body="Translate a text, open the Senses tab, and choose “Use this” on a sense you disagree with."
              />
            )}
            {locks.data && locks.data.length > 0 && (
              <ul>
                {locks.data.map((lock) => (
                  <li
                    key={lock.id}
                    className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 last:border-0"
                  >
                    <span className="text-[15px] font-medium text-ink">{lock.headword_norm}</span>
                    <Badge tone="neutral" mono>
                      {lock.pos}
                    </Badge>
                    <span aria-hidden="true" className="text-ink-faint">
                      →
                    </span>
                    <span className="text-[15px] text-ink">{lock.translation || '—'}</span>
                    <Badge tone="accent">{DOMAIN_TITLES[lock.domain_code] ?? lock.domain_code}</Badge>
                    <span className="max-w-lg truncate text-[11px] text-ink-faint italic">
                      {lock.gloss}
                    </span>
                    <Button
                      variant="danger"
                      size="sm"
                      className="ml-auto"
                      busy={unlocking.busy}
                      onClick={async () => {
                        const done = await unlocking.run(() =>
                          api.dictionary.unlockSense(lock.id),
                        )
                        if (done !== undefined) locks.reload()
                      }}
                    >
                      Remove
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Where the dictionary comes from"
          hint="The dictionary is real lexicographic data, not a hand-written word list, which is why the coverage figures mean something."
        />
        <div className="grid gap-4 px-4 py-3 text-xs leading-relaxed text-ink-muted sm:grid-cols-2">
          <p>
            <strong className="font-semibold text-ink">FreeDict eng-rus</strong>, released
            2025-11-23 under CC BY-SA 3.0 and extracted from Wiktionary:{' '}
            {stats ? thousands(stats.entries) : '62 000'} headwords,{' '}
            {stats ? thousands(stats.senses) : '78 000'} senses. Each sense keeps its English
            definition and its Wiktionary topic labels — <code>(computing)</code>,{' '}
            <code>(literature)</code>, <code>(archaic)</code> — which is what makes
            subject-area disambiguation possible at all.
          </p>
          <p>
            Russian morphology is <strong className="font-semibold text-ink">pymorphy3</strong>{' '}
            over the OpenCorpora dictionary; it both analyses the equivalents and generates the
            inflected forms. English analysis is{' '}
            <strong className="font-semibold text-ink">spaCy en_core_web_md</strong>. Nothing in
            the dictionary is edited by the system itself: every change here is yours, and every
            row you touch is flagged so a re-seed can tell them apart.
          </p>
        </div>
      </Card>
    </div>
  )
}

function NewEntryForm({
  busy,
  error,
  onDismissError,
  onSubmit,
  onCancel,
}: {
  busy: boolean
  error: string | undefined
  onDismissError: () => void
  onSubmit: (headword: string, pos: string, gloss: string, forms: string[]) => void
  onCancel: () => void
}) {
  const [headword, setHeadword] = useState('')
  const [pos, setPos] = useState('n')
  const [gloss, setGloss] = useState('')
  const [forms, setForms] = useState('')

  return (
    <form
      className="border-b border-line bg-accent-soft/25 px-4 py-3"
      onSubmit={(event) => {
        event.preventDefault()
        const parsed = forms
          .split(',')
          .map((form) => form.trim())
          .filter(Boolean)
        if (headword.trim() && parsed.length) onSubmit(headword.trim(), pos, gloss, parsed)
      }}
    >
      {error && (
        <div className="mb-3">
          <InlineError message={error} onDismiss={onDismissError} />
        </div>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="English headword" htmlFor="new-headword">
          <TextInput
            id="new-headword"
            value={headword}
            onChange={(event) => setHeadword(event.target.value)}
            placeholder="tokenizer"
            required
            className="min-w-48"
          />
        </Field>
        <Field
          label="Part of speech"
          htmlFor="new-pos"
          hint="Used to match the entry against the tag the analyser assigns, so a noun reading is never used for a verb."
        >
          <Select
            id="new-pos"
            value={pos}
            onChange={(event) => setPos(event.target.value)}
            className="min-w-40"
          >
            {POS_OPTIONS.filter(([value]) => value).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="Definition"
          htmlFor="new-gloss"
          hint="Optional, but a definition beginning with a topic label — (computing), (literature) — lets the disambiguator place the sense in a subject area."
        >
          <TextInput
            id="new-gloss"
            value={gloss}
            onChange={(event) => setGloss(event.target.value)}
            placeholder="(computing) A program that splits text into tokens."
            className="min-w-72"
          />
        </Field>
        <Field
          label="Russian equivalents"
          htmlFor="new-forms"
          hint="In order of preference, separated by commas. The translator uses the first one."
        >
          <TextInput
            id="new-forms"
            value={forms}
            onChange={(event) => setForms(event.target.value)}
            placeholder="токенизатор"
            required
            className="min-w-56"
          />
        </Field>
        <span className="flex gap-1.5">
          <Button type="submit" variant="primary" busy={busy}>
            Create
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </span>
      </div>
    </form>
  )
}
