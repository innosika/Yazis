import { useEffect, useRef, useState } from 'react'

import {
  Badge,
  Button,
  EmptyState,
  Hint,
  InlineError,
  Skeleton,
  TextInput,
} from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { classes, percent } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { useAction, useAsync } from '@/lib/useAsync'
import type { OovTerm, Suggestion } from '@/lib/types'

const SOURCE_NOTE: Record<Suggestion['source'], { label: string; tone: 'success' | 'info' | 'warning'; hint: string }> = {
  wiktionary: {
    label: 'Wiktionary',
    tone: 'success',
    hint: "Read from the English Wiktionary's translation table through the MediaWiki API — the most reliable of the three sources.",
  },
  derivation: {
    label: 'Derivation',
    tone: 'info',
    hint: 'Built from a Greco-Latin suffix correspondence (-tion → -ция, -ic → -ический) applied to the transcribed stem, then checked against the Russian morphological dictionary.',
  },
  transcription: {
    label: 'Transcription',
    tone: 'warning',
    hint: 'Practical transcription of the English spelling. Right for a name, a last resort for anything else — check it before accepting.',
  },
}

/**
 * The replenishment half of requirement R8.
 *
 * Words the translator could not resolve are queued automatically. This panel proposes a
 * Russian equivalent for each — from Wiktionary, from a derivational rule, or by
 * transcription — and shows which source answered and how much it can be trusted. Nothing
 * is written to the dictionary until the proposal is accepted, and the proposal is editable
 * before it is.
 */
export function OovQueue({ onEntryCreated }: { onEntryCreated: () => void }) {
  const { meta } = useMeta()
  const queue = useAsync(() => api.dictionary.oov('pending'), [])
  const { run, busy, error, clearError } = useAction()
  const [scanText, setScanText] = useState('')
  const [scanned, setScanned] = useState<number | null>(null)

  const refresh = () => {
    queue.reload()
    onEntryCreated()
  }

  return (
    <div>
      <div className="border-b border-line bg-raised px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="flex items-center gap-1.5 text-xs text-ink-muted">
            <strong className="font-semibold text-ink">
              {queue.data?.pending ?? 0} word{queue.data?.pending === 1 ? '' : 's'}
            </strong>
            waiting for a decision
            <Hint text="Every translation run adds the content words it could not resolve. Accepting one creates a dictionary entry, and the next translation of that word succeeds." />
          </p>
          <Button
            size="sm"
            busy={busy}
            onClick={async () => {
              const filled = await run(() => api.dictionary.fillSuggestions())
              if (filled) queue.setData(filled)
            }}
          >
            Propose translations
          </Button>
          <Button size="sm" variant="ghost" onClick={() => queue.reload()}>
            Refresh
          </Button>
          {meta && !meta.enrichment.wiktionary_enabled && (
            <Badge tone="warning">
              Wiktionary disabled — offline sources only
            </Badge>
          )}
        </div>

        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={async (event) => {
            event.preventDefault()
            if (!scanText.trim()) return
            const outcome = await run(() => api.dictionary.scan(scanText, 'cs'))
            if (outcome) {
              setScanned(outcome.found)
              queue.reload()
            }
          }}
        >
          <label htmlFor="scan" className="flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            Scan a text for gaps
            <Hint text="The batch form of the utility: it analyses the text, finds every content word the dictionary cannot translate, and queues a proposal for each. Useful before translating a long paper." />
          </label>
          <TextInput
            id="scan"
            value={scanText}
            onChange={(event) => setScanText(event.target.value)}
            placeholder="Paste a paragraph to check against the dictionary…"
            className="max-w-xl"
          />
          <Button type="submit" variant="secondary" busy={busy} disabled={!scanText.trim()}>
            Scan
          </Button>
          {scanned !== null && (
            <span className="nums text-xs text-ink-muted">{scanned} gaps found</span>
          )}
        </form>
      </div>

      {error && (
        <div className="p-3">
          <InlineError message={error} onDismiss={clearError} />
        </div>
      )}

      {queue.loading && <Skeleton rows={4} />}
      {queue.error && <InlineError message={queue.error} />}

      {queue.data && queue.data.items.length === 0 && (
        <EmptyState
          title="The queue is empty"
          body="Translate a text — any content word the dictionary cannot resolve will appear here with a proposed translation."
        />
      )}

      {queue.data && queue.data.items.length > 0 && (
        <ul>
          {queue.data.items.map((term) => (
            <QueueRow key={term.id} term={term} onDone={refresh} />
          ))}
        </ul>
      )}
    </div>
  )
}

function QueueRow({ term, onDone }: { term: OovTerm; onDone: () => void }) {
  const { run, busy, error, clearError } = useAction()
  // A proposal can arrive two ways: with the row (the batch "Propose translations" refetches
  // the whole queue) or from this row's own button. Local state holds only the second, so
  // that a refetched proposal is not shadowed by a stale copy of the first render's props.
  const [fetched, setFetched] = useState<Suggestion | null>(null)
  const suggestion = fetched ?? term.suggestion
  const [forms, setForms] = useState(suggestion?.forms.join(', ') ?? '')
  const edited = useRef(false)

  // Fill the field from whichever proposal is current, but never overwrite typing.
  useEffect(() => {
    if (suggestion && !edited.current) setForms(suggestion.forms.join(', '))
  }, [suggestion])

  const note = suggestion ? SOURCE_NOTE[suggestion.source] : null

  return (
    <li className="border-b border-line px-4 py-3 last:border-0">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-44">
          <p className="flex items-baseline gap-2">
            <span className="text-[15px] font-semibold text-ink">{term.lemma}</span>
            <Badge tone="neutral" mono>
              {term.pos}
            </Badge>
            {term.occurrences > 1 && (
              <span className="nums text-[11px] text-ink-faint">×{term.occurrences}</span>
            )}
          </p>
          {term.context && (
            <p className="mt-0.5 max-w-sm truncate text-[11px] text-ink-faint italic">
              {term.context}
            </p>
          )}
        </div>

        <div className="min-w-0 flex-1">
          {suggestion ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {note && (
                  <Badge tone={note.tone} title={note.hint}>
                    {note.label} · {percent(suggestion.confidence)}
                  </Badge>
                )}
                <TextInput
                  value={forms}
                  onChange={(event) => {
                    edited.current = true
                    setForms(event.target.value)
                  }}
                  aria-label={`Russian equivalents for ${term.lemma}`}
                  className="max-w-md"
                />
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
                {suggestion.explanation}
              </p>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                busy={busy}
                onClick={async () => {
                  const proposed = await run(() =>
                    api.dictionary.suggest(term.lemma, term.pos),
                  )
                  if (proposed) {
                    setFetched(proposed)
                    edited.current = false
                    setForms(proposed.forms.join(', '))
                  }
                }}
              >
                Propose a translation
              </Button>
              <TextInput
                value={forms}
                onChange={(event) => {
                  edited.current = true
                  setForms(event.target.value)
                }}
                placeholder="…or type the Russian equivalent yourself"
                aria-label={`Russian equivalents for ${term.lemma}`}
                className="max-w-md"
              />
            </div>
          )}
        </div>

        <span className="flex shrink-0 gap-1.5">
          <Button
            variant="primary"
            size="sm"
            busy={busy}
            disabled={!forms.trim()}
            onClick={async () => {
              const parsed = forms
                .split(',')
                .map((form) => form.trim())
                .filter(Boolean)
              const created = await run(() =>
                api.dictionary.accept(
                  term.id,
                  parsed,
                  suggestion ? `Added from ${suggestion.source}.` : 'Added by hand.',
                ),
              )
              if (created) onDone()
            }}
          >
            Accept
          </Button>
          <Button
            variant="ghost"
            size="sm"
            busy={busy}
            onClick={async () => {
              const done = await run(() => api.dictionary.dismiss(term.id))
              if (done !== undefined) onDone()
            }}
          >
            Dismiss
          </Button>
        </span>
      </div>

      {error && (
        <div className={classes('mt-2')}>
          <InlineError message={error} onDismiss={clearError} />
        </div>
      )}
    </li>
  )
}
