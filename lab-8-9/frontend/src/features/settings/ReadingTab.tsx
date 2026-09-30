import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { Segmented, Switch } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { useSettings } from '@/stores/settings'

import { Group, TabBody } from './SettingsSheet'

const EXAMPLE =
  'As shown by Vaswani et al. [12], self-attention costs O(n^2) for n tokens; with 16GB of RAM and a 1e-4 learning rate, see https://arxiv.org/abs/1706.03762 and Fig. 3b.'

export function ReadingTab() {
  const r = useSettings((s) => s.profile.reading)
  const setReading = useSettings((s) => s.setReading)
  const [text, setText] = useState(EXAMPLE)
  const spoken = useQuery({
    queryKey: ['spoken-preview', text, r],
    queryFn: () => api.spokenForm([text], r),
    placeholderData: (prev) => prev,
  })

  return (
    <TabBody title="Reading" intro="How the voice treats the parts of a paper that are not plain words. The preview shows the result as you change the rules.">
      <div className="grid gap-2 rounded-xl border border-line bg-surface p-4">
        <label htmlFor="preview" className="text-[12.5px] text-ink-muted">Written</label>
        <textarea
          id="preview"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          className="w-full resize-y bg-transparent font-serif text-[15px] leading-relaxed text-ink focus:outline-none"
        />
        <span className="mt-1 text-[12.5px] text-ink-muted">Spoken</span>
        <p className="font-serif text-[15px] leading-relaxed text-ink" aria-live="polite">
          {spoken.data?.spoken[0] ?? '…'}
        </p>
      </div>

      <Group title="Rules">
        <Segmented label="Citations like [12] or (Smith et al., 2020)" value={r.citations} onChange={(citations) => setReading({ citations })}
          options={[{ value: 'skip', label: 'Skip them' }, { value: 'read', label: 'Read them' }]} />
        <Segmented label="Formulas" value={r.math} onChange={(math) => setReading({ math })}
          options={[{ value: 'verbalize', label: 'Read in words' }, { value: 'skip', label: 'Say “a formula”' }]} />
        <Segmented label="Links" value={r.urls} onChange={(urls) => setReading({ urls })}
          options={[{ value: 'domain', label: 'Say the site' }, { value: 'link', label: 'Say “a link”' }, { value: 'skip', label: 'Skip them' }]} />
        <Segmented label="Acronyms" value={r.acronyms} onChange={(acronyms) => setReading({ acronyms })}
          options={[{ value: 'auto', label: 'Natural (SQL as “sequel”)' }, { value: 'spell', label: 'Spell every letter' }]} />
        <Switch label="Announce section numbers" description="“Section 3 point 2. Related work.” before each heading."
          checked={r.announce_headings} onChange={(announce_headings) => setReading({ announce_headings })} />
      </Group>
    </TabBody>
  )
}
