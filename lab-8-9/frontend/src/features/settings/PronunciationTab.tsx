import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, Volume2 } from 'lucide-react'
import { useState } from 'react'

import { Button, IconButton, inputClass } from '@/components/ui/primitives'
import { api } from '@/lib/api'
import { useLexicon } from '@/lib/queries'
import { usePlayer } from '@/stores/player'

import { Group, TabBody } from './SettingsSheet'

export function PronunciationTab() {
  const { data } = useLexicon()
  const qc = useQueryClient()
  const [term, setTerm] = useState('')
  const [sayAs, setSayAs] = useState('')
  const refresh = () => void qc.invalidateQueries({ queryKey: ['lexicon'] })
  const add = useMutation({
    mutationFn: () => api.addLexicon(term.trim(), sayAs.trim()),
    onSuccess: () => { setTerm(''); setSayAs(''); refresh() },
  })
  const remove = useMutation({ mutationFn: (id: number) => api.deleteLexicon(id), onSuccess: refresh })

  return (
    <TabBody
      title="Pronunciation"
      intro={`Teach the voice how to say names and terms. Lector already knows ${data?.builtin ?? 'about 200'} computer-science terms (SQL, LaTeX, PyTorch, ReLU…); your entries take priority.`}
    >
      <form
        className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => { e.preventDefault(); if (term.trim() && sayAs.trim()) add.mutate() }}
      >
        <label className="grid gap-1.5">
          <span className="text-[13px] text-ink">Written as</span>
          <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Kubernetes" className={inputClass} />
        </label>
        <label className="grid gap-1.5">
          <span className="text-[13px] text-ink">Say it as</span>
          <div className="flex gap-1">
            <input value={sayAs} onChange={(e) => setSayAs(e.target.value)} placeholder="koober netties" className={inputClass} />
            <IconButton type="button" label="Listen" disabled={!sayAs.trim()} onClick={() => void usePlayer.getState().readSnippet(sayAs)}>
              <Volume2 size={16} />
            </IconButton>
          </div>
        </label>
        <Button type="submit" variant="primary" disabled={!term.trim() || !sayAs.trim() || add.isPending}>Add</Button>
        <p className="text-[12px] text-ink-muted sm:col-span-3">Matched as a whole word and case-sensitive. Spell the sound with ordinary words or syllables.</p>
      </form>

      <Group title="Your words">
        {!data?.entries.length ? (
          <p className="text-[13px] text-ink-muted">None yet. You can also select a word in a document and choose “Pronounce as…”.</p>
        ) : (
          <ul className="grid divide-y divide-line rounded-xl border border-line bg-surface">
            {data.entries.map((e) => (
              <li key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                <span className="min-w-0 flex-1 truncate text-[14px] text-ink">{e.term}</span>
                <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink-muted">{e.say_as}</span>
                <IconButton label={`Listen to ${e.term}`} size="sm" onClick={() => void usePlayer.getState().readSnippet(e.term)}>
                  <Volume2 size={15} />
                </IconButton>
                <IconButton label={`Remove ${e.term}`} size="sm" onClick={() => remove.mutate(e.id)}>
                  <Trash2 size={15} />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </Group>
    </TabBody>
  )
}
