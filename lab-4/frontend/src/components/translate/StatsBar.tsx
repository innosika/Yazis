import { Hint } from '@/components/ui/primitives'
import { classes, coverageTone, milliseconds, percent, thousands } from '@/lib/format'
import type { Stats } from '@/lib/types'

const TONE_TEXT = {
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
} as const

/**
 * The numbers the assignment asks for, above the translation where they are read first:
 * words in the input, words translated, and the dictionary coverage those two imply.
 */
export function StatsBar({ stats, durationMs }: { stats: Stats; durationMs: number }) {
  const tone = coverageTone(stats.coverage)

  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6 print-block">
      <Tile
        label="Words"
        value={thousands(stats.words)}
        note={`${thousands(stats.content_words)} content words`}
        hint="Tokens that contain a letter or a digit: punctuation is not counted."
      />
      <Tile
        label="Translated"
        value={thousands(stats.translated_words)}
        note={`${thousands(stats.untranslated_words)} not in the dictionary`}
        hint="Words that resolved to a dictionary sense. A word absent from the dictionary stays in Latin script, or is transcribed if it is a name."
      />
      <Tile
        label="Coverage"
        value={percent(stats.coverage, 1)}
        valueClass={TONE_TEXT[tone]}
        note="of words needing the dictionary"
        hint="Translated words over the words that actually needed a dictionary. Articles, do-support and the possessive 's are excluded: Russian has no equivalent for them, so they are absent from the output by design, not by failure."
      />
      <Tile
        label="Sentences"
        value={thousands(stats.sentences)}
        note={`${thousands(stats.unique_lemmas)} distinct lemmas`}
        hint="Sentence boundaries come from the analyser, not from full stops alone."
      />
      <Tile
        label="Ambiguous"
        value={thousands(stats.ambiguous_words)}
        note="close sense decisions"
        hint="Words where the runner-up sense scored within one point of the winner. Review them on the Senses tab."
      />
      <Tile
        label="Rules applied"
        value={`${thousands(stats.dropped_tokens)} / ${thousands(stats.inserted_tokens)}`}
        note={`dropped / inserted · ${milliseconds(durationMs)}`}
        hint="Words the transfer rules removed (articles, auxiliaries, the possessive 's) and words they added (Russian prepositions, «будет», «должен»)."
      />
    </dl>
  )
}

function Tile({
  label,
  value,
  note,
  hint,
  valueClass,
}: {
  label: string
  value: string
  note: string
  hint: string
  valueClass?: string
}) {
  return (
    <div className="bg-surface px-3.5 py-3">
      <dt className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-ink-faint uppercase">
        {label}
        <Hint text={hint} />
      </dt>
      <dd className="mt-1">
        <span className={classes('nums text-[22px] leading-7 font-semibold tracking-tight', valueClass ?? 'text-ink')}>
          {value}
        </span>
        <span className="mt-0.5 block text-[11px] leading-4 text-ink-faint">{note}</span>
      </dd>
    </div>
  )
}
