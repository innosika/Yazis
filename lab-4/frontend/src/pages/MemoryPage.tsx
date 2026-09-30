import { useState } from 'react'

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
  TextInput,
} from '@/components/ui/primitives'
import { api, downloadText } from '@/lib/api'
import { dateTime, DOMAIN_TITLES, percent, thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { useAction, useAsync } from '@/lib/useAsync'
import type { MemoryMatch } from '@/lib/types'

/**
 * Additional feature 1, in full: the store behind the post-editing loop.
 *
 * The page exists because a translation memory is only useful if you can see into it —
 * check what a sentence would match before translating, correct a stored unit, carry the
 * memory to another machine.
 */
export function MemoryPage() {
  const { meta, reload: reloadMeta } = useMeta()
  const [query, setQuery] = useState('')
  const [domain, setDomain] = useState('')
  const [page, setPage] = useState(1)

  const units = useAsync(() => api.memory.list({ q: query, domain, page }), [query, domain, page])
  // The page reads its own statistics rather than the cached reference data: reuse counts
  // change on every translation, and a tile showing two reuses next to a row showing four
  // is worse than no tile at all.
  const memoryStats = useAsync(() => api.memory.stats(), [])
  const action = useAction()

  const [probe, setProbe] = useState('')
  const [probeDomain, setProbeDomain] = useState('cs')
  const [matches, setMatches] = useState<MemoryMatch[] | null>(null)

  const stats = memoryStats.data
  const thresholds = meta?.thresholds
  const pages = units.data ? Math.max(1, Math.ceil(units.data.total / units.data.per_page)) : 1

  const exportMemory = async () => {
    const all = await action.run(() => api.memory.exportAll())
    if (all) {
      downloadText(
        `translation-memory-${new Date().toISOString().slice(0, 10)}.json`,
        JSON.stringify(all, null, 2),
      )
    }
  }

  const importMemory = async (file: File | undefined) => {
    if (!file) return
    await action.run(async () => {
      const parsed = JSON.parse(await file.text())
      const rows = (Array.isArray(parsed) ? parsed : []).flatMap(
        (row: { source_text?: string; target_text?: string; domain_code?: string }) =>
          row.source_text && row.target_text
            ? [
                {
                  source_text: row.source_text,
                  target_text: row.target_text,
                  domain_code: row.domain_code ?? 'general',
                },
              ]
            : [],
      )
      if (rows.length === 0) throw new Error('No usable units found in that file.')
      await api.memory.importUnits(rows)
      units.reload()
      memoryStats.reload()
      reloadMeta()
    })
  }

  return (
    <div className="space-y-4">
      {stats && (
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
          {[
            ['Units', thousands(stats.units), 'Approved sentence pairs stored'],
            [
              'From post-editing',
              thousands(stats.post_edited),
              'Corrections you made in the translation view',
            ],
            ['Imported', thousands(stats.imported), 'Loaded from a file'],
            [
              'Reuses',
              thousands(stats.total_hits),
              'Times a stored translation replaced a machine one',
            ],
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

      {action.error && <InlineError message={action.error} onDismiss={action.clearError} />}

      <Card>
        <CardHeader
          title="Try a sentence against the memory"
          hint={
            thresholds
              ? `A similarity of ${percent(thresholds.tm_exact)} or above counts as exact and is applied automatically; ${percent(thresholds.tm_fuzzy)} and above is offered as a fuzzy match. Similarity is PostgreSQL trigram similarity over the normalised sentence.`
              : undefined
          }
          subtitle="The same lookup the translator performs for every sentence."
        />
        <form
          className="flex flex-wrap items-end gap-3 px-4 py-3"
          onSubmit={async (event) => {
            event.preventDefault()
            const found = await action.run(() => api.memory.search(probe, probeDomain))
            if (found) setMatches(found)
          }}
        >
          <Field label="English sentence" htmlFor="probe" className="flex-1">
            <TextInput
              id="probe"
              value={probe}
              onChange={(event) => setProbe(event.target.value)}
              placeholder="The main character of the novel is an unreliable narrator."
            />
          </Field>
          <Field label="Subject area" htmlFor="probe-domain">
            <Select
              id="probe-domain"
              value={probeDomain}
              onChange={(event) => setProbeDomain(event.target.value)}
              className="min-w-40"
            >
              {(meta?.domains ?? []).map((item) => (
                <option key={item.code} value={item.code}>
                  {item.title}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" variant="primary" busy={action.busy} disabled={!probe.trim()}>
            Search
          </Button>
        </form>

        {matches !== null && (
          <div className="border-t border-line">
            {matches.length === 0 ? (
              <EmptyState
                title="No match above the fuzzy threshold"
                body="This sentence would be translated from scratch."
              />
            ) : (
              <ul>
                {matches.map((match) => (
                  <li key={match.id} className="border-b border-line px-4 py-2.5 last:border-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={match.exact ? 'success' : 'info'}>
                        {percent(match.similarity, 1)} {match.exact ? '· exact' : '· fuzzy'}
                      </Badge>
                      <Badge tone="neutral">
                        {DOMAIN_TITLES[match.domain_code] ?? match.domain_code}
                      </Badge>
                      <span className="text-[11px] text-ink-faint">{match.origin}</span>
                    </div>
                    <p className="mt-1 text-sm text-ink-muted">{match.source_text}</p>
                    <p className="text-[15px] text-ink">{match.target_text}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3">
          <Field label="Filter" htmlFor="tm-search">
            <TextInput
              id="tm-search"
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setPage(1)
              }}
              placeholder="Words in the English sentence…"
              className="min-w-56"
            />
          </Field>
          <Field label="Subject area" htmlFor="tm-domain">
            <Select
              id="tm-domain"
              value={domain}
              onChange={(event) => {
                setDomain(event.target.value)
                setPage(1)
              }}
              className="min-w-40"
            >
              <option value="">All</option>
              {(meta?.domains ?? []).map((item) => (
                <option key={item.code} value={item.code}>
                  {item.title}
                </option>
              ))}
            </Select>
          </Field>
          <div className="ml-auto flex items-end gap-2">
            <Button busy={action.busy} onClick={() => void exportMemory()}>
              Export
            </Button>
            <label className="inline-flex">
              <span className="sr-only">Import a memory file</span>
              <input
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(event) => void importMemory(event.target.files?.[0])}
              />
              <span className="inline-flex h-9 cursor-pointer items-center rounded-md border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink hover:bg-sunken">
                Import
              </span>
            </label>
          </div>
        </div>

        {units.loading && <Skeleton rows={4} />}
        {units.error && (
          <div className="p-4">
            <InlineError message={units.error} />
          </div>
        )}

        {units.data && units.data.items.length === 0 && (
          <EmptyState
            title="The memory is empty"
            body="Translate a text, correct a sentence with “Post-edit”, and it will be stored here. The next time that sentence appears, your translation is used instead of the machine's."
          />
        )}

        {units.data && units.data.items.length > 0 && (
          <>
            <ul>
              {units.data.items.map((unit) => (
                <li key={unit.id} className="border-b border-line px-4 py-3 last:border-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={unit.origin === 'post-edit' ? 'accent' : 'neutral'}>
                      {unit.origin}
                    </Badge>
                    <Badge tone="neutral">
                      {DOMAIN_TITLES[unit.domain_code] ?? unit.domain_code}
                    </Badge>
                    {unit.hits > 0 && (
                      <span className="nums text-[11px] text-ink-faint">
                        reused {unit.hits}×
                      </span>
                    )}
                    <span className="nums ml-auto text-[11px] text-ink-faint">
                      {dateTime(unit.updated_at)}
                    </span>
                    <Button
                      variant="danger"
                      size="sm"
                      busy={action.busy}
                      onClick={async () => {
                        if (!window.confirm('Delete this memory unit?')) return
                        const done = await action.run(() => api.memory.remove(unit.id))
                        if (done !== undefined) {
                          units.reload()
                          memoryStats.reload()
                          reloadMeta()
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                  <p className="mt-1.5 rounded bg-source/50 px-2 py-1 text-sm text-ink">
                    {unit.source_text}
                  </p>
                  <p className="mt-1 rounded bg-target/50 px-2 py-1 text-[15px] text-ink">
                    {unit.target_text}
                  </p>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5">
              <span className="nums text-xs text-ink-faint">
                {thousands(units.data.total)} units · page {page} of {pages}
              </span>
              <span className="flex gap-1.5">
                <Button size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
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
      </Card>
    </div>
  )
}
