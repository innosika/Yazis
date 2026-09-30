import { useState } from 'react'

import { Badge, Button, EmptyState, Hint, InlineError } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { classes, DOMAIN_TITLES } from '@/lib/format'
import { useAction } from '@/lib/useAsync'
import type { Ambiguity, Candidate, DomainCode } from '@/lib/types'

/**
 * Additional feature 2: the disambiguator's reasoning, and the user's veto over it.
 *
 * Every ambiguous word is listed once with each sense it considered, the score that sense
 * received and the signals that produced that score. "Lock for this subject area" writes a
 * `sense_override`, which beats every signal on the next run - so a disagreement with the
 * system is resolved permanently in one click rather than argued with.
 */
export function SensesTab({
  ambiguities,
  domain,
  onLocked,
}: {
  ambiguities: Ambiguity[]
  domain: DomainCode
  onLocked: () => void
}) {
  const { run, busy, error, clearError } = useAction()
  const [locked, setLocked] = useState<Set<string>>(new Set())

  if (ambiguities.length === 0) {
    return (
      <EmptyState
        title="No close calls in this text"
        body="Every word either had a single dictionary sense, or one sense won by a clear margin. Words with more than one sense still appear in the word list, marked as ambiguous."
      />
    )
  }

  const lock = async (item: Ambiguity, candidate: Candidate) => {
    const done = await run(() =>
      api.dictionary.lockSense({
        headword: item.lemma,
        pos: candidate.entry_pos ?? 'n',
        domain_code: domain,
        sense_id: candidate.sense_id,
        translation_id: candidate.translation_id,
        note: `Chosen in the interface for ${DOMAIN_TITLES[domain]}`,
      }),
    )
    if (done !== undefined) {
      setLocked((previous) => new Set(previous).add(`${item.lemma}:${candidate.sense_id}`))
      onLocked()
    }
  }

  return (
    <div className="space-y-px bg-line">
      <div className="bg-raised px-4 py-2.5 text-xs leading-relaxed text-ink-muted">
        <p className="flex items-start gap-1.5">
          <span>
            {ambiguities.length} word{ambiguities.length === 1 ? '' : 's'} where the runner-up
            sense scored within one point of the winner, under{' '}
            <strong className="font-semibold text-ink">{DOMAIN_TITLES[domain]}</strong>. Locking a
            sense makes it the permanent choice for this subject area.
          </span>
          <Hint text="Score = 3.0 × topical label match + 1.2 × domain vocabulary + 1.5 × context overlap (Lesk) + 1.8 × syntactic fit + 0.6 × distributional similarity + 0.8 × dictionary order − 2.0 × competing-domain label − 2.5 × register penalty. Curated evidence outweighs statistics on purpose." />
        </p>
      </div>

      {error && (
        <div className="bg-surface p-3">
          <InlineError message={error} onDismiss={clearError} />
        </div>
      )}

      {ambiguities.map((item) => (
        <section key={`${item.lemma}-${item.upos}-${item.sentence}`} className="bg-surface px-4 py-3">
          <header className="mb-2 flex flex-wrap items-baseline gap-2">
            <h3 className="text-[15px] font-semibold text-ink">{item.text}</h3>
            <Badge tone="neutral">{item.pos_name}</Badge>
            <span className="nums text-[11px] text-ink-faint">
              margin {item.margin.toFixed(2)} · {item.candidates.length} senses shown
            </span>
            <span className="ml-auto max-w-2xl truncate text-[11px] text-ink-faint italic">
              {item.context}
            </span>
          </header>

          <ul className="space-y-1.5">
            {item.candidates.map((candidate) => (
              <CandidateRow
                key={candidate.sense_id}
                candidate={candidate}
                top={item.candidates[0].score}
                locked={locked.has(`${item.lemma}:${candidate.sense_id}`)}
                busy={busy}
                onLock={() => void lock(item, candidate)}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function CandidateRow({
  candidate,
  top,
  locked,
  busy,
  onLock,
}: {
  candidate: Candidate
  top: number
  locked: boolean
  busy: boolean
  onLock: () => void
}) {
  const [open, setOpen] = useState(false)
  const share = top > 0 ? Math.max(0, Math.min(1, candidate.score / top)) : 0

  return (
    <li
      className={classes(
        'rounded-md border px-3 py-2',
        candidate.selected || locked
          ? 'border-accent/45 bg-accent-soft/35'
          : 'border-line bg-raised',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="min-w-28 text-[15px] font-medium text-ink">
          {candidate.translation_accented || candidate.translation}
        </span>

        {candidate.selected && !locked && <Badge tone="accent">chosen</Badge>}
        {locked && <Badge tone="success">locked</Badge>}
        {candidate.locked && <Badge tone="success">locked earlier</Badge>}
        {candidate.labels.map((label) => (
          <Badge key={label} tone="info">
            {label}
          </Badge>
        ))}

        <span className="ml-auto flex items-center gap-2">
          <span className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-sunken sm:block">
            <span
              className={classes(
                'block h-full rounded-full',
                candidate.score > 0 ? 'bg-accent' : 'bg-danger',
              )}
              style={{ width: `${Math.abs(share) * 100}%` }}
            />
          </span>
          <span className="nums w-12 text-right text-xs font-semibold text-ink">
            {candidate.score.toFixed(2)}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
          >
            {open ? 'Hide why' : 'Why'}
          </Button>
          {!candidate.selected && !locked && (
            <Button variant="secondary" size="sm" busy={busy} onClick={onLock}>
              Use this
            </Button>
          )}
        </span>
      </div>

      {candidate.gloss && (
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">{candidate.gloss}</p>
      )}
      {candidate.alternatives.length > 0 && (
        <p className="mt-0.5 text-[11px] text-ink-faint">
          other equivalents of this sense: {candidate.alternatives.join(', ')}
        </p>
      )}

      {open && (
        <table className="mt-2 w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-line text-left text-ink-faint">
              <th scope="col" className="py-1 pr-3 font-medium">
                Signal
              </th>
              <th scope="col" className="py-1 pr-3 font-medium">
                Evidence
              </th>
              <th scope="col" className="py-1 pr-1 text-right font-medium">
                Value
              </th>
              <th scope="col" className="py-1 pr-1 text-right font-medium">
                Weight
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                Points
              </th>
            </tr>
          </thead>
          <tbody>
            {candidate.signals.map((signal, index) => (
              <tr key={index} className="border-b border-line/60 last:border-0">
                <td className="py-1 pr-3 font-medium text-ink">{signal.name}</td>
                <td className="py-1 pr-3 text-ink-muted">{signal.detail}</td>
                <td className="nums py-1 pr-1 text-right text-ink-muted">
                  {signal.value.toFixed(2)}
                </td>
                <td className="nums py-1 pr-1 text-right text-ink-faint">
                  ×{signal.weight.toFixed(1)}
                </td>
                <td
                  className={classes(
                    'nums py-1 text-right font-semibold',
                    signal.contribution >= 0 ? 'text-success' : 'text-danger',
                  )}
                >
                  {signal.contribution >= 0 ? '+' : ''}
                  {signal.contribution.toFixed(2)}
                </td>
              </tr>
            ))}
            <tr>
              <td colSpan={4} className="py-1 pr-1 text-right font-medium text-ink-faint">
                Total
              </td>
              <td className="nums py-1 text-right font-semibold text-ink">
                {candidate.score.toFixed(2)}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </li>
  )
}
