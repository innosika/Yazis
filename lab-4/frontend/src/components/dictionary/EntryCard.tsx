import { useState } from 'react'

import { Badge, Button, Hint, InlineError, TextInput } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { DOMAIN_TITLES } from '@/lib/format'
import { useAction } from '@/lib/useAsync'
import type { Entry, Sense } from '@/lib/types'

/**
 * One dictionary entry, editable in place.
 *
 * The order of a sense's equivalents is itself editable, and that is the most useful
 * correction the utility offers: the translator always takes the first equivalent, so
 * moving «статья» ahead of «бумага» for the academic sense of "paper" fixes every future
 * translation of that word in one action.
 */
export function EntryCard({
  entry,
  onChanged,
  onDeleted,
}: {
  entry: Entry
  onChanged: (entry: Entry) => void
  onDeleted: (id: number) => void
}) {
  const { run, busy, error, clearError } = useAction()
  const [adding, setAdding] = useState(false)

  return (
    <article className="border-b border-line px-4 py-3 last:border-0">
      <header className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-[15px] font-semibold text-ink">{entry.headword}</h3>
        {entry.pos && (
          <Badge tone="neutral" mono>
            {entry.pos}
          </Badge>
        )}
        {entry.ipa && <span className="font-mono text-[11px] text-ink-faint">{entry.ipa}</span>}
        {entry.word_count > 1 && <Badge tone="info">multiword unit</Badge>}
        {entry.is_user && <Badge tone="accent">edited by you</Badge>}
        <span className="nums ml-auto text-[11px] text-ink-faint">
          {entry.senses.length} sense{entry.senses.length === 1 ? '' : 's'}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setAdding((value) => !value)}
          aria-expanded={adding}
        >
          Add sense
        </Button>
        <Button
          variant="danger"
          size="sm"
          busy={busy}
          onClick={async () => {
            if (!window.confirm(`Delete the entry “${entry.headword}” and all its senses?`)) return
            const done = await run(() => api.dictionary.remove(entry.id))
            if (done !== undefined) onDeleted(entry.id)
          }}
        >
          Delete
        </Button>
      </header>

      {error && (
        <div className="mt-2">
          <InlineError message={error} onDismiss={clearError} />
        </div>
      )}

      {adding && (
        <NewSenseForm
          busy={busy}
          onCancel={() => setAdding(false)}
          onSubmit={async (gloss, forms) => {
            const updated = await run(() =>
              api.dictionary.addSense(entry.id, { gloss, labels: [], translations: forms }),
            )
            if (updated) {
              onChanged(updated)
              setAdding(false)
            }
          }}
        />
      )}

      <ol className="mt-2 space-y-2">
        {entry.senses.map((sense) => (
          <SenseRow
            key={sense.id}
            sense={sense}
            onChanged={onChanged}
            deletable={entry.senses.length > 1}
          />
        ))}
      </ol>
    </article>
  )
}

function SenseRow({
  sense,
  onChanged,
  deletable,
}: {
  sense: Sense
  onChanged: (entry: Entry) => void
  deletable: boolean
}) {
  const { run, busy, error, clearError } = useAction()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(sense.translations.map((item) => item.form_accented).join(', '))

  const domains = Object.entries(sense.domain_scores).filter(([, score]) => score > 0)

  return (
    <li className="rounded-md border border-line bg-raised px-3 py-2">
      <div className="flex flex-wrap items-start gap-2">
        <span className="nums mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-sunken text-[9px] font-bold text-ink-faint">
          {sense.idx + 1}
        </span>

        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex flex-wrap items-center gap-2">
              <TextInput
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                aria-label="Russian equivalents, in order, separated by commas"
                className="max-w-xl"
                autoFocus
              />
              <Button
                variant="primary"
                size="sm"
                busy={busy}
                onClick={async () => {
                  const forms = draft
                    .split(',')
                    .map((form) => form.trim())
                    .filter(Boolean)
                  if (forms.length === 0) return
                  const updated = await run(() =>
                    api.dictionary.setTranslations(sense.id, forms),
                  )
                  if (updated) {
                    onChanged(updated)
                    setEditing(false)
                  }
                }}
              >
                Save
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(sense.translations.map((item) => item.form_accented).join(', '))
                  setEditing(false)
                }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {sense.translations.map((translation, position) => (
                <span
                  key={translation.id}
                  className={
                    position === 0
                      ? 'text-[15px] font-medium text-ink'
                      : 'text-[15px] text-ink-muted'
                  }
                  title={position === 0 ? 'Used by the translator' : undefined}
                >
                  {translation.form_accented}
                  {position === 0 && sense.translations.length > 1 && (
                    <span className="ml-1 text-[10px] text-accent">◂ used</span>
                  )}
                </span>
              ))}
              {sense.translations.some((item) => item.is_user) && (
                <Badge tone="accent">yours</Badge>
              )}
            </p>
          )}

          {sense.gloss && (
            <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{sense.gloss}</p>
          )}

          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {sense.labels.map((label) => (
              <Badge key={label} tone="info">
                {label}
              </Badge>
            ))}
            {domains.map(([code, score]) => (
              <Badge
                key={code}
                tone="accent"
                title={`Affinity ${score.toFixed(2)} with ${DOMAIN_TITLES[code] ?? code}`}
              >
                {DOMAIN_TITLES[code] ?? code} {score.toFixed(2)}
              </Badge>
            ))}
          </div>
        </div>

        {!editing && (
          <span className="flex shrink-0 gap-1">
            <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
              Reorder / edit
              <Hint text="The translator always uses the first equivalent, so the order is part of the data. Type the equivalents in the order you want them, separated by commas." />
            </Button>
            {deletable && (
              <Button
                variant="danger"
                size="sm"
                busy={busy}
                onClick={async () => {
                  if (!window.confirm('Delete this sense?')) return
                  const updated = await run(() => api.dictionary.removeSense(sense.id))
                  if (updated) onChanged(updated)
                }}
              >
                Delete
              </Button>
            )}
          </span>
        )}
      </div>

      {error && (
        <div className="mt-2">
          <InlineError message={error} onDismiss={clearError} />
        </div>
      )}
    </li>
  )
}

function NewSenseForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean
  onSubmit: (gloss: string, forms: string[]) => void
  onCancel: () => void
}) {
  const [gloss, setGloss] = useState('')
  const [forms, setForms] = useState('')

  return (
    <form
      className="mt-2 grid gap-2 rounded-md border border-accent/40 bg-accent-soft/30 p-3 sm:grid-cols-[1fr_1fr_auto]"
      onSubmit={(event) => {
        event.preventDefault()
        const parsed = forms
          .split(',')
          .map((form) => form.trim())
          .filter(Boolean)
        if (parsed.length) onSubmit(gloss, parsed)
      }}
    >
      <TextInput
        value={gloss}
        onChange={(event) => setGloss(event.target.value)}
        placeholder="Definition, e.g. (computing) A program that splits text into tokens."
        aria-label="Definition of the new sense"
      />
      <TextInput
        value={forms}
        onChange={(event) => setForms(event.target.value)}
        placeholder="Russian equivalents, comma separated"
        aria-label="Russian equivalents of the new sense"
        required
      />
      <span className="flex gap-1.5">
        <Button type="submit" variant="primary" size="md" busy={busy}>
          Add
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </span>
    </form>
  )
}
