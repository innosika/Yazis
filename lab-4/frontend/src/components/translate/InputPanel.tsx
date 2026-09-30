import { useRef, useState } from 'react'

import {
  Badge,
  Button,
  Card,
  Field,
  Hint,
  SegmentedControl,
  Select,
} from '@/components/ui/primitives'
import { thousands } from '@/lib/format'
import { useMeta } from '@/lib/meta-context'
import type { DomainCode, Mode, Sample } from '@/lib/types'

export interface InputState {
  text: string
  domain: DomainCode
  mode: Mode
  useMemory: boolean
}

export function InputPanel({
  state,
  onChange,
  samples,
  onTranslate,
  busy,
}: {
  state: InputState
  onChange: (next: InputState) => void
  samples: Sample[]
  onTranslate: () => void
  busy: boolean
}) {
  const { meta } = useMeta()
  const fileInput = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string>('')
  const limit = meta?.thresholds.max_input_chars ?? 60000
  const tooLong = state.text.length > limit

  const patch = (partial: Partial<InputState>) => onChange({ ...state, ...partial })

  const loadFile = async (file: File | undefined) => {
    if (!file) return
    const text = await file.text()
    setFileName(file.name)
    // An .html upload is stripped to its text so the tagger is not fed markup.
    patch({ text: file.name.endsWith('.html') ? stripHtml(text) : text })
  }

  const domains = meta?.domains ?? []

  return (
    <Card className="no-print">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-end gap-3">
          <Field
            label="Subject area"
            htmlFor="domain"
            hint="Variant 1 covers computer-science articles and literary essays. The subject area decides which sense of an ambiguous word is chosen: 'character' is «персонаж» in a literary text and «знак» in a technical one."
          >
            <Select
              id="domain"
              value={state.domain}
              onChange={(event) => patch({ domain: event.target.value as DomainCode })}
              className="min-w-44"
            >
              {domains.map((domain) => (
                <option key={domain.code} value={domain.code}>
                  {domain.title}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Architecture"
            hint="Transfer analyses the sentence, disambiguates every word, generates Russian forms and rebuilds the structure. Direct substitutes the dictionary's first equivalent word by word — the classical «пословный перевод», kept as the honest baseline."
          >
            <SegmentedControl<Mode>
              label="Translation architecture"
              value={state.mode}
              onChange={(mode) => patch({ mode })}
              options={[
                { value: 'transfer', label: 'Transfer', title: 'Full analysis and generation' },
                { value: 'direct', label: 'Direct', title: 'Word-for-word substitution' },
              ]}
            />
          </Field>

          <Field
            label="Translation memory"
            hint="When on, a sentence you have already approved is reused instead of being translated again, and a similar sentence is offered with a match percentage."
          >
            <SegmentedControl<'on' | 'off'>
              label="Use the translation memory"
              value={state.useMemory ? 'on' : 'off'}
              onChange={(value) => patch({ useMemory: value === 'on' })}
              options={[
                { value: 'on', label: 'On' },
                { value: 'off', label: 'Off' },
              ]}
            />
          </Field>
        </div>

        <div className="flex items-end gap-2">
          <Field label="Sample text" htmlFor="sample">
            <Select
              id="sample"
              value=""
              onChange={(event) => {
                const sample = samples.find((item) => item.name === event.target.value)
                if (sample) {
                  setFileName('')
                  patch({ text: sample.text, domain: sample.domain })
                }
              }}
              className="min-w-56"
            >
              <option value="">Choose a sample…</option>
              {samples.map((sample) => (
                <option key={sample.name} value={sample.name}>
                  {sample.title}
                </option>
              ))}
            </Select>
          </Field>
          <Button onClick={() => fileInput.current?.click()} title="Load a .txt or .html file">
            <UploadIcon />
            Upload
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".txt,.html,.htm,text/plain,text/html"
            className="hidden"
            onChange={(event) => void loadFile(event.target.files?.[0])}
          />
        </div>
      </div>

      <div className="p-4">
        <label htmlFor="source" className="sr-only">
          English text to translate
        </label>
        <textarea
          id="source"
          value={state.text}
          onChange={(event) => patch({ text: event.target.value })}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') onTranslate()
          }}
          placeholder="Paste English text here, choose a sample above, or upload a .txt file…"
          spellCheck={false}
          rows={7}
          className="scroll-thin w-full resize-y rounded-md border border-line-strong bg-raised px-3 py-2.5 font-sans text-[15px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-accent"
        />

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-faint">
            <span className="nums">
              {thousands(state.text.length)} / {thousands(limit)} characters
            </span>
            {fileName && <Badge tone="neutral">{fileName}</Badge>}
            {tooLong && <Badge tone="danger">Too long — trim the text before translating</Badge>}
            <span className="hidden items-center gap-1 sm:flex">
              <kbd className="rounded border border-line bg-sunken px-1 font-mono text-[10px]">
                Ctrl
              </kbd>
              +
              <kbd className="rounded border border-line bg-sunken px-1 font-mono text-[10px]">
                Enter
              </kbd>
              to translate
            </span>
          </div>

          <div className="flex items-center gap-2">
            {state.text && (
              <Button variant="ghost" size="sm" onClick={() => patch({ text: '' })}>
                Clear
              </Button>
            )}
            <Button
              variant="primary"
              onClick={onTranslate}
              busy={busy}
              disabled={!state.text.trim() || tooLong}
            >
              Translate
              <Hint text="Runs analysis, dictionary lookup, disambiguation, morphological generation and syntactic transfer. Typically under a second for a page of text." />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  )
}

function stripHtml(html: string): string {
  const parsed = new DOMParser().parseFromString(html, 'text/html')
  parsed.querySelectorAll('script, style, nav, footer, header').forEach((node) => node.remove())
  return (parsed.body?.textContent ?? '').replace(/\n{3,}/g, '\n\n').trim()
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <path strokeLinecap="round" d="M8 10.5V2.5m0 0L5.2 5.3M8 2.5l2.8 2.8M2.5 11v1.8a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V11" />
    </svg>
  )
}
