import { useEffect, useState } from 'react'

import { Badge, Button, Hint } from '@/components/ui/primitives'
import { classes, percent } from '@/lib/format'
import type { Piece, Sentence, TokenInfo } from '@/lib/types'

/**
 * One sentence, in both languages, with three things layered on top of the text.
 *
 * *Alignment.* Hovering a Russian word highlights the English word or words it came from,
 * and the other way round. In a rule-based system this mapping is exact rather than
 * guessed, so showing it costs nothing and answers the first question a reader has.
 *
 * *Post-editing.* The translation is editable in place. Saving stores it in the
 * translation memory, which is what makes the next run of the same text instant and
 * correct - additional feature 1.
 *
 * *Provenance.* A memory match says so, with its percentage; a word the rules dropped or
 * inserted is listed under "what the rules did", so nothing in the output is unexplained.
 */
export function SentenceCard({
  sentence,
  tokens,
  onSave,
  saving,
}: {
  sentence: Sentence
  tokens: TokenInfo[]
  onSave: (source: string, target: string) => Promise<void>
  saving: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(sentence.target)
  const [hovered, setHovered] = useState<number[] | null>(null)
  const [showRules, setShowRules] = useState(false)

  useEffect(() => {
    setDraft(sentence.target)
    setEditing(false)
  }, [sentence.target])

  // Layout tokens carry the newlines between sentences: real in the source, meaningless
  // in the rendering, and they would otherwise appear as empty tooltipped spans.
  const sourceTokens = tokens.filter((token) => token.upos !== 'SPACE' && token.text.trim())
  const visible = sentence.pieces.filter(
    (piece) => piece.kind !== 'dropped' && piece.surface.trim(),
  )
  const dropped = sentence.pieces.filter((piece) => piece.kind === 'dropped')
  const inserted = visible.filter(
    (piece) => piece.kind === 'auxiliary' || piece.kind === 'preposition',
  )
  const match = sentence.memory
  const dirty = draft.trim() !== sentence.target.trim()
  // An exact memory match replaces the machine output entirely. The pieces still describe
  // what the machine *would* have produced, so they must not be rendered here - the
  // alignment of a human translation is unknown, and showing the machine's words under a
  // "reused" badge would be a plain contradiction.
  const fromMemory = Boolean(match?.exact)

  return (
    <article className="print-block overflow-hidden rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line bg-raised px-3 py-1.5">
        <span className="nums text-[11px] font-semibold text-ink-faint">
          {String(sentence.index + 1).padStart(2, '0')}
        </span>

        {match && (
          <Badge tone={match.exact ? 'success' : 'info'} title={match.source_text}>
            {match.exact ? 'Memory · exact' : `Memory · ${percent(match.similarity)}`}
          </Badge>
        )}
        {match?.exact && (
          <span className="text-[11px] text-ink-faint">
            approved translation reused
            <Hint text="This sentence is identical to one you have already approved, so the stored translation is used instead of a fresh machine translation." />
          </span>
        )}

        <div className="ml-auto flex items-center gap-1.5 no-print">
          {(dropped.length > 0 || inserted.length > 0) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowRules((value) => !value)}
              aria-expanded={showRules}
            >
              {showRules ? 'Hide' : 'What the rules did'}
              <span className="nums text-ink-faint">
                {dropped.length + inserted.length}
              </span>
            </Button>
          )}
          {editing ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDraft(sentence.target)
                  setEditing(false)
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                busy={saving}
                disabled={!draft.trim()}
                onClick={async () => {
                  await onSave(sentence.source, draft)
                  setEditing(false)
                }}
              >
                Save to memory
              </Button>
            </>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
              <PencilIcon />
              Post-edit
            </Button>
          )}
        </div>
      </header>

      <div className="grid gap-px bg-line md:grid-cols-2">
        <div className="bg-source/60 px-3.5 py-3">
          <p className="mb-1.5 text-[10px] font-semibold tracking-wider text-source-ink uppercase">
            English
          </p>
          <p className="text-[15px] leading-7 text-ink">
            {sourceTokens.map((token) => (
              <span
                key={token.index}
                onMouseEnter={() => setHovered([token.index])}
                onMouseLeave={() => setHovered(null)}
                className={classes(
                  'rounded px-0.5 transition-colors',
                  hovered?.includes(token.index) && 'bg-accent-soft text-accent-soft-ink',
                  token.dropped_by_rule && 'text-ink-faint line-through decoration-ink-faint/50',
                  !token.translated &&
                    !token.dropped_by_rule &&
                    token.upos !== 'PUNCT' &&
                    'underline decoration-danger decoration-wavy decoration-1 underline-offset-2',
                )}
                title={describeToken(token)}
              >
                {token.text}{' '}
              </span>
            ))}
          </p>
        </div>

        <div className="bg-target/60 px-3.5 py-3">
          <p className="mb-1.5 text-[10px] font-semibold tracking-wider text-target-ink uppercase">
            Russian
          </p>
          {editing ? (
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              rows={3}
              autoFocus
              spellCheck={false}
              aria-label={`Russian translation of sentence ${sentence.index + 1}`}
              className="w-full resize-y rounded-md border border-accent bg-surface px-2.5 py-2 text-[15px] leading-7 text-ink"
            />
          ) : fromMemory ? (
            <p className="text-[15px] leading-7 text-ink">{sentence.target}</p>
          ) : (
            <p className="text-[15px] leading-7 text-ink">
              {visible.length === 0 ? (
                <span className="text-ink-faint italic">no output</span>
              ) : (
                visible.map((piece, index) => (
                  <PieceSpan
                    key={index}
                    piece={piece}
                    highlighted={
                      hovered !== null &&
                      piece.source_indices.some((source) => hovered.includes(source))
                    }
                    onHover={setHovered}
                  />
                ))
              )}
            </p>
          )}
          {dirty && !editing && (
            <p className="mt-1 text-[11px] text-warning">unsaved edit</p>
          )}
        </div>
      </div>

      {showRules && (
        <div className="grid gap-px border-t border-line bg-line text-xs md:grid-cols-2">
          <RuleList
            title="Dropped"
            hint="Present in the English, deliberately absent from the Russian."
            items={dropped.map((piece) => ({ text: piece.source_text, note: piece.note }))}
          />
          <RuleList
            title="Inserted or governed"
            hint="Added by the transfer rules, or given a case by them."
            items={inserted.map((piece) => ({
              text: piece.surface,
              note: piece.note || (piece.case ? `${piece.case} case` : ''),
            }))}
          />
        </div>
      )}
    </article>
  )
}

const KIND_STYLES: Record<Piece['kind'], string> = {
  word: '',
  punct: '',
  function: 'text-info',
  preposition: 'text-accent',
  auxiliary: 'text-accent italic',
  untranslated: 'font-mono text-[13px] text-danger',
  dropped: 'hidden',
}

function PieceSpan({
  piece,
  highlighted,
  onHover,
}: {
  piece: Piece
  highlighted: boolean
  onHover: (indices: number[] | null) => void
}) {
  const glue = piece.kind === 'punct' && /^[.,;:!?)»…]/.test(piece.surface)
  return (
    <>
      {!glue && ' '}
      <span
        onMouseEnter={() => onHover(piece.source_indices)}
        onMouseLeave={() => onHover(null)}
        title={describePiece(piece)}
        className={classes(
          'rounded px-0.5 transition-colors',
          KIND_STYLES[piece.kind],
          highlighted && 'bg-accent-soft text-accent-soft-ink',
        )}
      >
        {piece.surface}
      </span>
    </>
  )
}

function RuleList({
  title,
  hint,
  items,
}: {
  title: string
  hint: string
  items: { text: string; note: string }[]
}) {
  return (
    <div className="bg-surface px-3.5 py-2.5">
      <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold text-ink-muted">
        {title}
        <Hint text={hint} />
      </p>
      {items.length === 0 ? (
        <p className="text-ink-faint">—</p>
      ) : (
        <ul className="space-y-1">
          {items.map((item, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-1.5">
              <code className="rounded bg-sunken px-1 font-mono text-[11px] text-ink">
                {item.text}
              </code>
              <span className="text-[11px] text-ink-muted">{item.note || '—'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function describeToken(token: TokenInfo): string {
  const parts = [`${token.text} — ${token.pos_name} (${token.tag}: ${token.tag_name})`]
  if (token.lemma !== token.text.toLowerCase()) parts.push(`lemma: ${token.lemma}`)
  if (token.features.length) parts.push(token.features.join(', '))
  if (token.translation) parts.push(`→ ${token.translation}`)
  if (token.note) parts.push(token.note)
  return parts.join('\n')
}

function describePiece(piece: Piece): string {
  const parts = [`${piece.surface} ← ${piece.source_text || '(added by a rule)'}`]
  if (piece.lemma && piece.lemma !== piece.surface) parts.push(`dictionary form: ${piece.lemma}`)
  if (piece.decoded.length) parts.push(piece.decoded.join(', '))
  if (piece.note) parts.push(piece.note)
  return parts.join('\n')
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path strokeLinecap="round" d="M11.2 2.4 13.6 4.8 5.6 12.8 2.4 13.6l.8-3.2 8-8Z" />
    </svg>
  )
}
