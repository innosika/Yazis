import { useMemo, useState } from 'react'

import { CompareTab } from '@/components/translate/CompareTab'
import { InputPanel, type InputState } from '@/components/translate/InputPanel'
import { SensesTab } from '@/components/translate/SensesTab'
import { SentenceCard } from '@/components/translate/SentenceCard'
import { StatsBar } from '@/components/translate/StatsBar'
import { TreeTab } from '@/components/translate/TreeTab'
import { WordsTab } from '@/components/translate/WordsTab'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Hint,
  InlineError,
  SegmentedControl,
  Skeleton,
  Tabs,
} from '@/components/ui/primitives'
import { api, downloadText } from '@/lib/api'
import { DOMAIN_TITLES, thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import { useAction, useAsync } from '@/lib/useAsync'
import type { TranslateResult } from '@/lib/types'

type Tab = 'translation' | 'words' | 'tree' | 'senses' | 'compare'

export function TranslatePage() {
  const { meta, reload: reloadMeta } = useMeta()
  const samples = useAsync(() => api.samples(), [])

  const [input, setInput] = useState<InputState>({
    text: '',
    domain: 'cs',
    mode: 'transfer',
    useMemory: true,
  })
  const [result, setResult] = useState<TranslateResult | null>(null)
  const [tab, setTab] = useState<Tab>('translation')
  const [view, setView] = useState<'sentences' | 'continuous'>('sentences')

  const translation = useAction()
  const saving = useAction()
  const exporting = useAction()

  const translate = async () => {
    const next = await translation.run(() =>
      api.translate({
        text: input.text,
        domain: input.domain,
        mode: input.mode,
        include_direct: true,
        use_memory: input.useMemory,
        save: true,
      }),
    )
    if (next) {
      setResult(next)
      setTab('translation')
    }
  }

  const saveToMemory = async (source: string, target: string) => {
    await saving.run(async () => {
      await api.memory.save({
        source_text: source,
        target_text: target,
        domain_code: input.domain,
      })
      // Re-translating is how the saved unit becomes visible everywhere at once: the
      // sentence itself, the memory badge, and the hit counter in the header.
      const next = await api.translate({
        text: input.text,
        domain: input.domain,
        mode: input.mode,
        include_direct: true,
        use_memory: true,
        save: false,
      })
      setResult(next)
      reloadMeta()
    })
  }

  const exportTxt = async () => {
    const file = await exporting.run(() =>
      api.exportTxt({
        text: input.text,
        domain: input.domain,
        mode: input.mode,
        include_direct: true,
        use_memory: input.useMemory,
        save: false,
        title: titleFor(input.text),
      }),
    )
    if (file) downloadText(file.filename, file.content)
  }

  const tabs = useMemo(
    () =>
      [
        { value: 'translation' as Tab, label: 'Translation' },
        { value: 'words' as Tab, label: 'Words', count: result?.words.length },
        { value: 'tree' as Tab, label: 'Parse tree', count: result?.trees.length },
        { value: 'senses' as Tab, label: 'Senses', count: result?.ambiguities.length },
        { value: 'compare' as Tab, label: 'Architectures' },
      ].filter(Boolean),
    [result],
  )

  return (
    <div className="space-y-4">
      <InputPanel
        state={input}
        onChange={setInput}
        samples={samples.data ?? []}
        onTranslate={() => void translate()}
        busy={translation.busy}
      />

      {translation.error && (
        <InlineError message={translation.error} onDismiss={translation.clearError} />
      )}
      {saving.error && <InlineError message={saving.error} onDismiss={saving.clearError} />}
      {exporting.error && (
        <InlineError message={exporting.error} onDismiss={exporting.clearError} />
      )}

      {translation.busy && !result && <Skeleton rows={5} className="rounded-lg border border-line bg-surface" />}

      {!result && !translation.busy && (
        <Card>
          <EmptyState
            title="Nothing translated yet"
            body="Paste an English text above, or pick one of the two bundled samples — a computer-science article and a literary essay, the two subject areas of variant 1."
            action={
              meta ? (
                <p className="mt-2 text-[11px] text-ink-faint">
                  Dictionary ready: {thousands(meta.dictionary.entries)} headwords,{' '}
                  {thousands(meta.dictionary.senses)} senses,{' '}
                  {thousands(meta.dictionary.multiword_units)} multiword units.
                </p>
              ) : undefined
            }
          />
        </Card>
      )}

      {result && (
        <>
          <StatsBar stats={result.stats} durationMs={result.duration_ms} />

          <Card>
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-2 pr-4">
              <Tabs tabs={tabs} active={tab} onChange={setTab} />
              <div className="ml-auto flex items-center gap-2 py-2 no-print">
                <Badge tone="neutral" title="Subject area used for this translation">
                  {DOMAIN_TITLES[result.domain]}
                </Badge>
                <Badge tone={result.mode === 'transfer' ? 'accent' : 'warning'}>
                  {result.mode === 'transfer' ? 'Transfer' : 'Direct'}
                </Badge>
                {result.memory_hits > 0 && (
                  <Badge tone="info" title="Sentences matched in the translation memory">
                    {result.memory_hits} memory {result.memory_hits === 1 ? 'match' : 'matches'}
                  </Badge>
                )}
                <Button size="sm" busy={exporting.busy} onClick={() => void exportTxt()}>
                  <DownloadIcon />
                  Export .txt
                  <Hint text="A Unicode text file with the translation, the statistics, the frequency-ordered word list with grammatical information, and the tag decoding. Saved with a byte-order mark so Windows Notepad shows Cyrillic correctly." />
                </Button>
                <Button size="sm" onClick={() => window.print()}>
                  <PrintIcon />
                  Print
                </Button>
              </div>
            </div>

            <div role="tabpanel">
              {tab === 'translation' && (
                <div className="p-4">
                  <div className="mb-3 flex flex-wrap items-center gap-3 no-print">
                    <SegmentedControl<'sentences' | 'continuous'>
                      label="Translation view"
                      value={view}
                      onChange={setView}
                      options={[
                        { value: 'sentences', label: 'Sentence by sentence' },
                        { value: 'continuous', label: 'Continuous text' },
                      ]}
                    />
                    <p className="text-[11px] leading-relaxed text-ink-faint">
                      Hover a word to see where it came from. Click <em>Post-edit</em> to correct a
                      sentence — your correction is stored and reused.
                    </p>
                  </div>

                  {view === 'continuous' ? (
                    <div className="grid gap-4 lg:grid-cols-2">
                      <article className="print-block rounded-lg border border-source-line bg-source/50 p-4">
                        <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-source-ink uppercase">
                          Source — English
                        </h3>
                        <p className="text-[15px] leading-8 whitespace-pre-wrap text-ink">
                          {result.source}
                        </p>
                      </article>
                      <article className="print-block rounded-lg border border-target-line bg-target/50 p-4">
                        <h3 className="mb-2 text-[10px] font-semibold tracking-wider text-target-ink uppercase">
                          Translation — Russian
                        </h3>
                        <p className="text-[15px] leading-8 whitespace-pre-wrap text-ink">
                          {result.target}
                        </p>
                      </article>
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {result.sentences.map((sentence) => (
                        <SentenceCard
                          key={sentence.index}
                          sentence={sentence}
                          tokens={result.tokens.filter(
                            (token) => token.sentence === sentence.index,
                          )}
                          saving={saving.busy}
                          onSave={saveToMemory}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {tab === 'words' && <WordsTab words={result.words} />}
              {tab === 'tree' && <TreeTab trees={result.trees} tokens={result.tokens} />}
              {tab === 'senses' && (
                <SensesTab
                  ambiguities={result.ambiguities}
                  domain={result.domain}
                  onLocked={() => void translate()}
                />
              )}
              {tab === 'compare' && (
                <CompareTab sentences={result.sentences} directTarget={result.direct_target} />
              )}
            </div>
          </Card>

          {result.oov.length > 0 && (
            <Card className="no-print">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
                <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  Words the dictionary could not translate
                  <Hint text="Queued for the replenishment utility on the Dictionary page, where the system proposes a Russian equivalent for each and you accept or correct it." />
                </h2>
                <a
                  href="#/dictionary"
                  className="ml-auto text-xs font-medium text-accent hover:underline"
                >
                  Open the dictionary utility →
                </a>
              </div>
              <ul className="flex flex-wrap gap-1.5 p-4">
                {result.oov.map((mention) => (
                  <li key={`${mention.lemma}-${mention.upos}`}>
                    <Badge tone="danger" title={`${mention.upos} · ${mention.context}`}>
                      {mention.lemma}
                      {mention.occurrences > 1 && (
                        <span className="nums opacity-70">×{mention.occurrences}</span>
                      )}
                    </Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function titleFor(text: string): string {
  const first = text.trim().split(/\s+/).slice(0, 6).join(' ')
  return first.replace(/[^\p{L}\p{N} -]/gu, '') || 'translation'
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path strokeLinecap="round" d="M8 2.5v8m0 0L5.2 7.7M8 10.5l2.8-2.8M2.5 11v1.8a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V11" />
    </svg>
  )
}

function PrintIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path d="M4.5 6V2.5h7V6M4.5 11.5h7V14h-7z" />
      <path d="M4.5 6h-2v5h2m7-5h2v5h-2" />
    </svg>
  )
}
