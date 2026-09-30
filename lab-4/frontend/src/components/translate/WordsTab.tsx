import { useMemo, useState } from 'react'

import { Badge, Button, EmptyState, Hint, TextInput } from '@/components/ui/primitives'
import { classes } from '@/lib/format'
import type { WordRow } from '@/lib/types'

type SortKey = 'count' | 'lemma' | 'upos' | 'translation'
type Filter = 'all' | 'untranslated' | 'ambiguous' | 'dropped'

/**
 * Tab 1 of the assignment: "a list of words ordered by frequency of occurrence in the text
 * with their translations into the output language and grammatical information".
 *
 * Counted over (lemma, part of speech) pairs rather than surface forms, so "model" and
 * "models" are one row with a count of two - and the forms actually seen are listed, because
 * a reader checking the table against the text needs to find the word as it was written.
 */
export function WordsTab({ words }: { words: WordRow[] }) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<SortKey>('count')
  const [ascending, setAscending] = useState(false)

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const filtered = words.filter((row) => {
      if (filter === 'untranslated' && (row.translated || row.dropped_by_rule)) return false
      if (filter === 'ambiguous' && !row.ambiguous) return false
      if (filter === 'dropped' && !row.dropped_by_rule) return false
      if (!needle) return true
      return (
        row.lemma.includes(needle) ||
        row.translation.toLowerCase().includes(needle) ||
        row.forms.some((form) => form.toLowerCase().includes(needle)) ||
        row.gloss.toLowerCase().includes(needle)
      )
    })

    const direction = ascending ? 1 : -1
    return [...filtered].sort((left, right) => {
      switch (sort) {
        case 'count':
          return (left.count - right.count) * direction || left.lemma.localeCompare(right.lemma)
        case 'lemma':
          return left.lemma.localeCompare(right.lemma) * direction
        case 'upos':
          return (
            left.upos.localeCompare(right.upos) * direction ||
            right.count - left.count
          )
        case 'translation':
          return left.translation.localeCompare(right.translation, 'ru') * direction
      }
    })
  }, [words, query, filter, sort, ascending])

  const counts = useMemo(
    () => ({
      all: words.length,
      untranslated: words.filter((row) => !row.translated && !row.dropped_by_rule).length,
      ambiguous: words.filter((row) => row.ambiguous).length,
      dropped: words.filter((row) => row.dropped_by_rule).length,
    }),
    [words],
  )

  const toggleSort = (key: SortKey) => {
    if (key === sort) setAscending((value) => !value)
    else {
      setSort(key)
      setAscending(key === 'lemma')
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 no-print">
        <TextInput
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter by English word, Russian word or definition…"
          aria-label="Filter the word list"
          className="max-w-xs"
        />
        <div className="flex flex-wrap gap-1">
          {(['all', 'untranslated', 'ambiguous', 'dropped'] as Filter[]).map((option) => (
            <Button
              key={option}
              size="sm"
              variant={filter === option ? 'primary' : 'ghost'}
              onClick={() => setFilter(option)}
            >
              {LABELS[option]}
              <span className="nums opacity-70">{counts[option]}</span>
            </Button>
          ))}
        </div>
        <span className="nums ml-auto text-xs text-ink-faint">
          {rows.length} of {words.length} rows
        </span>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="No words match"
          body="Clear the filter or choose a different category above."
        />
      ) : (
        <div className="scroll-thin max-h-[68vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-raised">
              <tr className="border-b border-line text-left">
                <Th className="w-10 text-right">#</Th>
                <Th sortable active={sort === 'count'} ascending={ascending} onClick={() => toggleSort('count')} className="w-16 text-right">
                  Freq
                </Th>
                <Th sortable active={sort === 'lemma'} ascending={ascending} onClick={() => toggleSort('lemma')}>
                  English
                </Th>
                <Th sortable active={sort === 'upos'} ascending={ascending} onClick={() => toggleSort('upos')} className="w-44">
                  <span className="inline-flex items-center gap-1.5">
                    Part of speech
                    <Hint text="The coarse Universal tag, then the fine Penn Treebank tag in brackets with its decoding. English marks tense, number and degree on the fine tag." />
                  </span>
                </Th>
                <Th sortable active={sort === 'translation'} ascending={ascending} onClick={() => toggleSort('translation')} className="w-52">
                  Russian
                </Th>
                <Th>
                  <span className="inline-flex items-center gap-1.5">
                    Grammatical information
                    <Hint text="The morphological features the analyser found, plus the dictionary sense the equivalent came from." />
                  </span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={`${row.lemma}-${row.upos}`}
                  className="border-b border-line align-top last:border-0 hover:bg-raised"
                >
                  <td className="nums px-3 py-2 text-right text-xs text-ink-faint">{index + 1}</td>
                  <td className="nums px-3 py-2 text-right font-semibold text-ink">{row.count}</td>
                  <td className="px-3 py-2">
                    <span className="font-medium text-ink">{row.lemma}</span>
                    {row.forms.length > 1 || row.forms[0] !== row.lemma ? (
                      <span className="mt-0.5 block text-[11px] text-ink-faint">
                        as written: {row.forms.join(', ')}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-ink">{row.pos_name}</span>
                    <span className="mt-0.5 block text-[11px] text-ink-faint">
                      <code className="font-mono">{row.tag}</code> · {row.tag_name}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {row.dropped_by_rule ? (
                      <Badge tone="neutral" title={row.note}>
                        dropped by a rule
                      </Badge>
                    ) : row.translated ? (
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[15px] text-ink">
                          {row.translation_accented || row.translation}
                        </span>
                        {row.from_user && <Badge tone="accent">yours</Badge>}
                        {row.ambiguous && (
                          <Badge tone="warning" title={`${row.sense_count} senses considered`}>
                            ambiguous
                          </Badge>
                        )}
                      </span>
                    ) : (
                      <Badge tone="danger" title={row.note}>
                        not in the dictionary
                      </Badge>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs leading-relaxed text-ink-muted">
                    {row.features.length > 0 && (
                      <span className="block">{row.features.join(' · ')}</span>
                    )}
                    {row.gloss && (
                      <span className="mt-0.5 block text-ink-faint italic">
                        {row.gloss}
                        {row.sense_count > 1 && (
                          <span className="nums not-italic">
                            {' '}
                            (sense {row.sense_index + 1} of {row.sense_count})
                          </span>
                        )}
                      </span>
                    )}
                    {!row.gloss && !row.features.length && (
                      <span className="text-ink-faint">{row.note || '—'}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const LABELS: Record<Filter, string> = {
  all: 'All',
  untranslated: 'Not translated',
  ambiguous: 'Ambiguous',
  dropped: 'Dropped',
}

function Th({
  children,
  className,
  sortable,
  active,
  ascending,
  onClick,
}: {
  children: React.ReactNode
  className?: string
  sortable?: boolean
  active?: boolean
  ascending?: boolean
  onClick?: () => void
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (ascending ? 'ascending' : 'descending') : undefined}
      className={classes(
        'px-3 py-2 text-[11px] font-semibold tracking-wide text-ink-faint uppercase',
        className,
      )}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onClick}
          className={classes(
            'inline-flex items-center gap-1 uppercase transition-colors hover:text-ink',
            active && 'text-accent',
          )}
        >
          {children}
          <span aria-hidden="true" className="text-[9px]">
            {active ? (ascending ? '▲' : '▼') : '⇅'}
          </span>
        </button>
      ) : (
        children
      )}
    </th>
  )
}
