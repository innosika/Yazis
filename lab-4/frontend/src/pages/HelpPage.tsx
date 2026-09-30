import { useState } from 'react'

import {
  Badge,
  Card,
  CardHeader,
  InlineError,
  Skeleton,
  Tabs,
  TextInput,
} from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { useAsync } from '@/lib/useAsync'

type Tab = 'guide' | 'how' | 'tags' | 'rules'

export function HelpPage() {
  const [tab, setTab] = useState<Tab>('guide')

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-2">
        <Tabs
          tabs={[
            { value: 'guide' as Tab, label: 'Using the system' },
            { value: 'how' as Tab, label: 'How it translates' },
            { value: 'tags' as Tab, label: 'Tag reference' },
            { value: 'rules' as Tab, label: 'Transfer rules' },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>
      {tab === 'guide' && <Guide />}
      {tab === 'how' && <HowItWorks />}
      {tab === 'tags' && <TagReference />}
      {tab === 'rules' && <RuleReference />}
    </Card>
  )
}

/* ------------------------------------------------------------------------------- guide */

function Guide() {
  const { meta } = useMeta()

  return (
    <div className="prose-none max-w-4xl space-y-6 px-4 py-5 text-sm leading-relaxed text-ink-muted">
      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">What this is</h2>
        <p>
          A machine-translation workbench for <strong className="text-ink">English → Russian</strong>,
          built for laboratory work 4, variant 1. The two subject areas the variant names —
          scientific articles on computer science, and literary essays — are not decoration:
          they change which sense of an ambiguous word the system chooses.
        </p>
        <p className="mt-2">
          Translation is <strong className="text-ink">rule-based</strong>, not neural. Every step is
          inspectable: you can see the tag on each word, the sense the disambiguator picked and
          why, the Russian ending it generated, and the rule that moved a word. A neural model
          would translate more fluently and explain nothing — and it could not satisfy the
          assignment, which asks for per-word grammatical information, an editable dictionary and
          a parse tree.
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">Translating a text</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>
            Paste English text, upload a <code>.txt</code> or <code>.html</code> file, or pick one
            of the bundled samples.
          </li>
          <li>
            Choose the <strong className="text-ink">subject area</strong>. This is the single
            control that most changes the output: “character” becomes «персонаж» under Literature
            and «знак» under Computer Science.
          </li>
          <li>
            Leave the architecture on <strong className="text-ink">Transfer</strong> for real
            translation. Switch to <strong className="text-ink">Direct</strong> to see the
            word-for-word baseline — useful for the defence, not for reading.
          </li>
          <li>
            Press <strong className="text-ink">Translate</strong>, or Ctrl+Enter in the text box.
          </li>
        </ol>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">The five result tabs</h2>
        <dl className="space-y-2.5">
          {[
            [
              'Translation',
              'Both languages side by side, sentence by sentence. Hovering a word highlights the word it came from. Press Post-edit to correct a sentence — the correction is stored and reused.',
            ],
            [
              'Words',
              'The frequency-ordered word list the assignment asks for: every word of the input with its count, its part-of-speech tag and that tag’s decoding, its Russian equivalent and the dictionary sense it came from. Sortable and filterable.',
            ],
            [
              'Parse tree',
              'The syntactic parse tree of whichever sentence you choose, drawn from the dependency analysis, with a token table underneath.',
            ],
            [
              'Senses',
              'Every word where the sense decision was close, with the score each sense received and the evidence behind it. “Use this” locks your choice for the subject area, permanently.',
            ],
            [
              'Architectures',
              'The same sentence through both systems, and what each stage of the transfer pipeline changed.',
            ],
          ].map(([name, body]) => (
            <div key={name} className="grid gap-1 sm:grid-cols-[130px_1fr] sm:gap-4">
              <dt className="font-semibold text-ink">{name}</dt>
              <dd>{body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">Saving and printing</h2>
        <p>
          <strong className="text-ink">Export .txt</strong> writes a Unicode text file containing
          the statistics, the translation sentence by sentence, the word-for-word version, the
          frequency-ordered word list with grammatical information, the tag decoding, and the list
          of words the dictionary could not translate. It is saved with a byte-order mark so that
          Windows Notepad shows Cyrillic rather than mojibake.{' '}
          <strong className="text-ink">Print</strong> lays the same results out for paper.
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">
          Fixing the dictionary when it is wrong
        </h2>
        <p>
          Two things go wrong with a dictionary-driven translator: a word is missing, or the wrong
          equivalent is listed first. The <strong className="text-ink">Dictionary</strong> page
          handles both.
        </p>
        <ul className="mt-2 list-disc space-y-1.5 pl-5">
          <li>
            <strong className="text-ink">Missing words</strong> land in the replenishment queue
            automatically. The system proposes a Russian equivalent — from Wiktionary, from a
            Greco-Latin suffix correspondence, or by practical transcription — and tells you which
            source answered and how far to trust it. You accept, edit, or dismiss.
          </li>
          <li>
            <strong className="text-ink">Wrong order</strong> is fixed by editing a sense’s
            equivalents: the translator always takes the first one, so moving «статья» ahead of
            «бумага» corrects every future translation of that sense.
          </li>
        </ul>
      </section>

      {meta && (
        <section className="rounded-md border border-line bg-raised p-3.5 text-xs">
          <h2 className="mb-1.5 text-sm font-semibold text-ink">This installation</h2>
          <ul className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            <li>
              Dictionary: {thousands(meta.dictionary.entries)} headwords,{' '}
              {thousands(meta.dictionary.senses)} senses,{' '}
              {thousands(meta.dictionary.translations)} Russian equivalents,{' '}
              {thousands(meta.dictionary.multiword_units)} multiword units
            </li>
            <li>
              Translation memory: {thousands(meta.memory.units)} units,{' '}
              {thousands(meta.memory.total_hits)} reuses
            </li>
            <li>
              Memory thresholds: exact at {(meta.thresholds.tm_exact * 100).toFixed(0)}%, fuzzy
              from {(meta.thresholds.tm_fuzzy * 100).toFixed(0)}%
            </li>
            <li>
              Automatic replenishment from Wiktionary:{' '}
              {meta.enrichment.wiktionary_enabled ? 'enabled' : 'disabled (offline sources only)'}
            </li>
          </ul>
        </section>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- how it works */

const PIPELINE = [
  [
    '1 · Analysis',
    'spaCy en_core_web_md segments the text, tokenises it, and gives every token a lemma, a Universal part-of-speech tag, a Penn Treebank tag, morphological features and a syntactic head. Nothing Russian exists yet — this is the «анализ» half of a transfer system, carried out entirely in the categories of the source language.',
  ],
  [
    '2 · Lexical transfer',
    'Every dictionary unit in the sentence is looked up, multiword units first and longest: “machine learning” is found before “machine”. Lookup is by lemma and part of speech together, so a noun reading is never used for a verb. A word with no entry is recorded as a gap and left visible in the output.',
  ],
  [
    '3 · Disambiguation',
    'An entry usually has several senses, and the sense decides the equivalent. Six signals are weighed: the Wiktionary topic label on the sense, the subject area’s own vocabulary, the overlap between the sense’s definition and the surrounding sentence (the Lesk method), whether the sense’s syntactic labels fit what the parse shows, distributional similarity from the word vectors, and the dictionary’s own sense order. Register labels — archaic, obsolete, rare — count against a sense; a label from a competing subject area counts against it too. A sense you have locked wins outright.',
  ],
  [
    '4 · Morphological generation',
    'The dictionary gives a lemma; Russian needs a form. pymorphy3 generates it from the case, number, gender, tense and person the transfer stage asks for. Agreement is propagated down the dependency tree: adjectives and participles take gender, number and case from their head noun, finite verbs take person and number from their subject, and past-tense verbs take the subject’s gender — which English never marks, so the value has to come from the Russian noun.',
  ],
  [
    '5 · Syntactic transfer',
    'The structure is rebuilt. Articles, do-support, the infinitive marker and the present-tense copula are dropped, because Russian has no equivalent for any of them. Each dependency role implies a case; prepositions override it with their own government, and a few Russian verbs override it again — «управлять» takes an instrumental where English “control” takes a plain object. Nominal modifiers and possessives move behind their head as genitives: “network model” becomes «модель сети», “the author’s narrative” becomes «повествование автора».',
  ],
  [
    '6 · Output',
    'Pieces are joined with Russian spacing and punctuation, the first letter is capitalised, and each piece keeps a link back to the source tokens that produced it — which is what the alignment highlighting and the per-word grammatical information are built on.',
  ],
] as const

function HowItWorks() {
  return (
    <div className="max-w-4xl space-y-5 px-4 py-5 text-sm leading-relaxed text-ink-muted">
      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">The two architectures</h2>
        <p>
          The methodology divides machine-translation systems into direct systems, indirect
          systems with a transfer step or an interlingua, and knowledge-based systems. Both of the
          first two are implemented here, over the same dictionary, so they can be compared on the
          same input.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-line bg-raised p-3">
            <Badge tone="warning">Direct</Badge>
            <p className="mt-1.5 text-xs">
              Each element found in the dictionary is replaced by its first equivalent. No
              translation model, no analysis, no agreement, no reordering — “translation requires a
              minimum of transformations”. Its output is the honest measure of how much the rest of
              the pipeline is doing.
            </p>
          </div>
          <div className="rounded-md border border-accent/40 bg-accent-soft/30 p-3">
            <Badge tone="accent">Transfer</Badge>
            <p className="mt-1.5 text-xs">
              Correspondences are established after the syntactic structure of the sentence has
              been identified. Analysis works in the categories of English, generation in the
              categories of Russian, and an explicit transfer step connects them.
            </p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">The pipeline, stage by stage</h2>
        <ol className="space-y-3">
          {PIPELINE.map(([title, body]) => (
            <li key={title} className="rounded-md border border-line bg-raised p-3">
              <h3 className="text-[13px] font-semibold text-ink">{title}</h3>
              <p className="mt-1 text-xs">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="mb-2 text-base font-semibold text-ink">What the system does badly</h2>
        <p>
          A dictionary-driven translator has limits worth naming rather than hiding.{' '}
          <strong className="text-ink">Aspect</strong> is chosen from the tense alone, because
          English does not mark it. <strong className="text-ink">Sense order</strong> inside an
          entry is the lexicographer’s, so an equivalent that is right for a scientific article can
          sit second — “paper” gives «бумага» before «статья». Long sentences with several
          subordinate clauses get their cases right and their word order only approximately.{' '}
          <strong className="text-ink">Coreference</strong> is not resolved, so possessives stay
          «его» where a human would write «свой».
        </p>
        <p className="mt-2">
          All four are visible in the interface rather than papered over, and three of them can be
          corrected permanently: lock a sense, reorder a sense’s equivalents, or post-edit the
          sentence so the memory answers next time.
        </p>
      </section>
    </div>
  )
}

/* ----------------------------------------------------------------------------- reference */

function TagReference() {
  const tagsets = useAsync(() => api.tagsets(), [])
  const [filter, setFilter] = useState('')

  if (tagsets.loading) return <Skeleton rows={6} />
  if (tagsets.error) {
    return (
      <div className="p-4">
        <InlineError message={tagsets.error} />
      </div>
    )
  }
  if (!tagsets.data) return null

  const needle = filter.trim().toLowerCase()
  const keep = (code: string, name: string, description: string) =>
    !needle ||
    code.toLowerCase().includes(needle) ||
    name.toLowerCase().includes(needle) ||
    description.toLowerCase().includes(needle)

  return (
    <div>
      <div className="border-b border-line px-4 py-2.5">
        <TextInput
          type="search"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter every tag, name and description…"
          aria-label="Filter the tag reference"
          className="max-w-sm"
        />
      </div>

      <div className="grid gap-px bg-line lg:grid-cols-2">
        <TagTable
          title="Universal part of speech"
          note="The coarse tag the translator branches on."
          rows={tagsets.data.upos.filter((tag) => keep(tag.code, tag.name, tag.description))}
        />
        <TagTable
          title="Penn Treebank"
          note="The fine tag. For English this is where tense, number and degree live."
          rows={tagsets.data.penn.filter((tag) => keep(tag.code, tag.name, tag.description))}
        />
        <TagTable
          title="OpenCorpora"
          note="The tagset of the Russian forms this system generates."
          rows={tagsets.data.opencorpora.filter((tag) => keep(tag.code, tag.name, tag.description))}
        />
        <div className="bg-surface">
          <header className="border-b border-line px-4 py-2.5">
            <h3 className="text-sm font-semibold text-ink">Dependency relations</h3>
            <p className="mt-0.5 text-[11px] text-ink-faint">
              The edge labels in the parse tree. Each one implies a Russian case.
            </p>
          </header>
          <table className="w-full border-collapse text-sm">
            <tbody>
              {tagsets.data.dependencies
                .filter((row) => keep(row.code, row.description, ''))
                .map((row) => (
                  <tr key={row.code} className="border-b border-line last:border-0">
                    <td className="w-28 px-4 py-1.5 align-top">
                      <code className="font-mono text-[11px] text-ink">{row.code}</code>
                    </td>
                    <td className="px-4 py-1.5 text-xs text-ink-muted">{row.description}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function TagTable({
  title,
  note,
  rows,
}: {
  title: string
  note: string
  rows: { code: string; name: string; description: string; examples: string }[]
}) {
  return (
    <div className="bg-surface">
      <header className="border-b border-line px-4 py-2.5">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <p className="mt-0.5 text-[11px] text-ink-faint">{note}</p>
      </header>
      <table className="w-full border-collapse text-sm">
        <tbody>
          {rows.map((tag) => (
            <tr key={tag.code} className="border-b border-line last:border-0">
              <td className="w-20 px-4 py-1.5 align-top">
                <code className="font-mono text-[11px] font-semibold text-ink">{tag.code}</code>
              </td>
              <td className="px-4 py-1.5">
                <span className="text-xs font-medium text-ink">{tag.name}</span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-muted">
                  {tag.description}
                  {tag.examples && (
                    <span className="text-ink-faint italic"> — {tag.examples}</span>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RuleReference() {
  const rules = useAsync(() => api.rules(), [])

  if (rules.loading) return <Skeleton rows={6} />
  if (rules.error) {
    return (
      <div className="p-4">
        <InlineError message={rules.error} />
      </div>
    )
  }
  if (!rules.data) return null

  return (
    <div className="grid gap-px bg-line lg:grid-cols-2">
      <section className="bg-surface">
        <CardHeader
          title="Prepositions and the cases they govern"
          subtitle="“— (case only)” means the preposition disappears and only the ending survives."
        />
        <div className="scroll-thin max-h-[60vh] overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 bg-raised">
              <tr className="border-b border-line text-left">
                {['English', 'Russian', 'Case'].map((heading) => (
                  <th
                    key={heading}
                    scope="col"
                    className="px-4 py-2 text-[11px] font-semibold tracking-wide text-ink-faint uppercase"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...rules.data.compound_prepositions, ...rules.data.prepositions].map((row) => (
                <tr key={row.english} className="border-b border-line last:border-0">
                  <td className="px-4 py-1.5 text-ink">{row.english}</td>
                  <td className="px-4 py-1.5 text-ink">{row.russian}</td>
                  <td className="px-4 py-1.5">
                    <Badge tone="neutral">{row.case}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="flex flex-col gap-px bg-line">
        <section className="bg-surface">
          <CardHeader
            title="Dependency role → case"
            subtitle="Applied when no preposition governs the word."
          />
          <table className="w-full border-collapse text-sm">
            <tbody>
              {rules.data.dependency_cases.map((row) => (
                <tr key={row.dependency} className="border-b border-line last:border-0">
                  <td className="w-40 px-4 py-1.5">
                    <code className="font-mono text-[11px] text-ink">{row.dependency}</code>
                  </td>
                  <td className="px-4 py-1.5">
                    <Badge tone="neutral">{row.case}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="bg-surface">
          <CardHeader
            title="Register penalties"
            subtitle="How hard each label argues against a sense being the intended one."
          />
          <table className="w-full border-collapse text-sm">
            <tbody>
              {rules.data.register_penalties.map((row) => (
                <tr key={row.label} className="border-b border-line last:border-0">
                  <td className="px-4 py-1.5 text-ink">{row.label}</td>
                  <td className="px-4 py-1.5">
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-sunken">
                        <span
                          className="block h-full rounded-full bg-danger"
                          style={{ width: `${row.penalty * 100}%` }}
                        />
                      </span>
                      <span className="nums text-xs text-ink-muted">
                        −{(row.penalty * 2.5).toFixed(2)}
                      </span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  )
}
