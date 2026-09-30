import { Badge, EmptyState, Hint } from '@/components/ui/primitives'
import type { Sentence } from '@/lib/types'

/**
 * The classification of machine-translation systems from the assignment, made visible.
 *
 * The methodology distinguishes direct systems, which "replace all of the text's elements
 * found in the dictionary with their translation equivalents", from indirect systems with a
 * transfer step, where "translation correspondences are established not directly, but after
 * the syntactic and semantic structure of each sentence has been identified in analysis".
 *
 * Both are implemented, and this tab runs them on the same input and shows what each stage
 * of the transfer pipeline changed - so the difference between the two architectures is
 * something you read off the screen rather than take on trust.
 */
const STAGE_NOTES: Record<string, string> = {
  analysis:
    'Tokens with their Penn Treebank tags, straight from the analyser. Nothing Russian exists yet.',
  'lexical transfer':
    'Each dictionary unit replaced by the equivalent the disambiguator chose — in dictionary form, in English word order. This is where a direct system stops.',
  'morphological generation':
    'Russian endings generated: case from the syntactic role, agreement propagated from heads to their dependents.',
  'syntactic transfer':
    'Structure rebuilt: articles and auxiliaries dropped, prepositions mapped to their governed case, nominal modifiers moved behind their head as genitives.',
}

export function CompareTab({
  sentences,
  directTarget,
}: {
  sentences: Sentence[]
  directTarget: string
}) {
  if (sentences.length === 0) {
    return <EmptyState title="Nothing to compare" body="Translate a text first." />
  }

  const hasDirect = Boolean(directTarget)

  return (
    <div className="space-y-px bg-line">
      {hasDirect && (
        <section className="bg-surface px-4 py-3">
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
            The two architectures on the whole text
            <Hint text="Same input, same dictionary, same disambiguation. The only difference is whether the system rebuilds the sentence or substitutes word by word." />
          </h3>
          <div className="grid gap-3 lg:grid-cols-2">
            <Panel
              title="Direct — word-for-word"
              tone="warning"
              note="First dictionary equivalent for every word, no disambiguation, no endings, no reordering, articles left in place."
              text={directTarget}
            />
            <Panel
              title="Transfer — analysis and generation"
              tone="success"
              note="Senses chosen for the subject area, Russian forms generated, structure rebuilt."
              text={sentences.map((sentence) => sentence.target).join(' ')}
            />
          </div>
        </section>
      )}

      {sentences.map((sentence) => {
        const stages = Object.entries(sentence.stages)
        return (
          <section key={sentence.index} className="bg-surface px-4 py-3">
            <header className="mb-2 flex flex-wrap items-baseline gap-2">
              <span className="nums text-[11px] font-semibold text-ink-faint">
                {String(sentence.index + 1).padStart(2, '0')}
              </span>
              <p className="flex-1 text-sm text-ink">{sentence.source}</p>
            </header>

            <ol className="space-y-1.5">
              {stages.map(([name, value], index) => (
                <li key={name} className="grid gap-1.5 sm:grid-cols-[190px_1fr] sm:gap-3">
                  <div className="flex items-start gap-1.5">
                    <span className="nums mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-sunken text-[9px] font-bold text-ink-faint">
                      {index + 1}
                    </span>
                    <span className="text-[11px] leading-4 font-medium text-ink-muted">
                      {name}
                      {STAGE_NOTES[name] && <Hint text={STAGE_NOTES[name]} />}
                    </span>
                  </div>
                  <p
                    className={
                      name === 'analysis'
                        ? 'scroll-thin overflow-x-auto rounded bg-sunken px-2 py-1 font-mono text-[11px] whitespace-nowrap text-ink-muted'
                        : 'rounded bg-raised px-2 py-1 text-[14px] leading-relaxed text-ink'
                    }
                  >
                    {value || <span className="text-ink-faint">—</span>}
                  </p>
                </li>
              ))}
              {sentence.direct && (
                <li className="grid gap-1.5 sm:grid-cols-[190px_1fr] sm:gap-3">
                  <div className="flex items-start gap-1.5">
                    <span className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-warning-soft text-[9px] font-bold text-warning">
                      ≠
                    </span>
                    <span className="text-[11px] leading-4 font-medium text-warning">
                      direct architecture
                      <Hint text="What the same sentence becomes with no analysis: the baseline the transfer pipeline has to beat." />
                    </span>
                  </div>
                  <p className="rounded bg-warning-soft/50 px-2 py-1 text-[14px] leading-relaxed text-ink">
                    {sentence.direct}
                  </p>
                </li>
              )}
            </ol>
          </section>
        )
      })}
    </div>
  )
}

function Panel({
  title,
  note,
  text,
  tone,
}: {
  title: string
  note: string
  text: string
  tone: 'warning' | 'success'
}) {
  return (
    <div className="rounded-md border border-line bg-raised p-3">
      <p className="mb-1.5 flex items-center gap-2">
        <Badge tone={tone}>{title}</Badge>
      </p>
      <p className="text-[15px] leading-7 text-ink">{text}</p>
      <p className="mt-2 border-t border-line pt-2 text-[11px] leading-relaxed text-ink-faint">
        {note}
      </p>
    </div>
  )
}
