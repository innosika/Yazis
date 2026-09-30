import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AudioLines, Pencil, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useRef, useState } from 'react'

import { Button, cx, IconButton, inputClass, Modal, Segmented, Spinner, Switch } from '@/components/ui/primitives'
import { api, type CustomCommandIn } from '@/lib/api'
import { useCommands, useVoices } from '@/lib/queries'
import type { CommandInfo, Lang, MatchOutcome, Recognition } from '@/lib/types'
import { usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'

import { LANGUAGES } from './ListeningTab'
import { Group, TabBody } from './SettingsSheet'

const CATEGORY_TITLES: Record<CommandInfo['category'], string> = {
  playback: 'Playback',
  navigation: 'Moving around',
  voice: 'Voice and sound',
  assistant: 'Questions',
  app: 'App',
  custom: 'Your commands',
}

const ACTION_LABELS: Record<string, string> = {
  play: 'Start reading', pause: 'Pause', resume: 'Resume', stop: 'Stop', repeat: 'Repeat sentence',
  start_over: 'Start over', next_sentence: 'Next sentence', previous_sentence: 'Previous sentence',
  next_paragraph: 'Next paragraph', previous_paragraph: 'Previous paragraph', next_section: 'Next section',
  go_to_section: 'Go to section number', read_abstract: 'Read the abstract', set_speed: 'Set speed to',
  normal_speed: 'Normal speed', faster: 'Faster', slower: 'Slower', louder: 'Louder', quieter: 'Quieter',
  set_volume: 'Set volume % to', mute: 'Mute', unmute: 'Unmute', switch_voice: 'Switch voice to',
  next_voice: 'Next voice', set_pitch: 'Set pitch (semitones) to', where_am_i: 'Say where I am',
  time_left: 'Say time left', summarize: 'Summarize section', read_clipboard: 'Read clipboard',
  open_library: 'Open library', dark_mode: 'Dark mode', light_mode: 'Light mode',
  show_commands: 'Show commands', stop_listening: 'Stop listening', say: 'Say text',
}

// --------------------------------------------------------------------- tester

function OutcomeView({ outcome, transcript, extra }: { outcome: MatchOutcome | null; transcript?: string; extra?: string }) {
  if (!outcome) return null
  const m = outcome.match
  return (
    <div className="grid gap-1 rounded-lg bg-sunken px-3 py-2.5 text-[13px]">
      {transcript !== undefined && <p className="text-ink">Heard “{transcript}”</p>}
      {m ? (
        <p className="text-ink">
          <span className="font-medium text-success">{m.title}</span>
          {Object.keys(m.slots).length > 0 && (
            <span className="text-ink-muted">
              {' '}with {Object.entries(m.slots).filter(([k]) => !k.endsWith('_block') && k !== 'section').map(([k, v]) => `${k.replace('_', ' ')} ${v}`).join(', ')}
            </span>
          )}
        </p>
      ) : (
        <p className="text-ink-muted">
          No command.{' '}
          {outcome.suggestions[0] && outcome.suggestions[0].confidence > 0.5 && <>Closest: “{outcome.suggestions[0].phrase}” ({Math.round(outcome.suggestions[0].confidence * 100)}%).</>}
        </p>
      )}
      <p className="text-[12px] text-ink-faint">
        {m ? `Matched by ${m.method === 'llm' ? 'the language model' : m.method === 'template' ? 'phrase' : 'similarity'}, ${Math.round(m.confidence * 100)}% sure. ` : ''}
        Normalized to “{outcome.normalized}”, stages: {outcome.stages.join(' → ')}, {Math.round(outcome.match_ms)} ms.{extra ? ` ${extra}` : ''}
      </p>
    </div>
  )
}

function Tester({ lang }: { lang: Lang }) {
  const [text, setText] = useState('')
  const [outcome, setOutcome] = useState<MatchOutcome | null>(null)
  const [recognition, setRecognition] = useState<Recognition | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const docId = usePlayer((s) => s.doc?.id ?? null)
  const listening = useSettings((s) => s.profile.listening)
  const test = useMutation({
    mutationFn: (t: string) => api.testCommand(t, lang, docId, listening.llm_fallback),
    onSuccess: (o) => { setOutcome(o); setRecognition(null); setError(null) },
    onError: (e: Error) => setError(e.message),
  })
  const recognize = useMutation({
    mutationFn: (file: File) =>
      api.recognize(file, { language: lang, mode: 'command', engine: listening.engine, playing: false, played_text: '', document_id: docId, llm_fallback: listening.llm_fallback }),
    onSuccess: (r) => { setRecognition(r); setOutcome(null); setError(null) },
    onError: (e: Error) => setError(e.message),
  })
  return (
    <div className="grid gap-3 rounded-xl border border-line bg-surface p-4">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) test.mutate(text.trim()) }}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Try a phrase, e.g. “could you slow down a bit”" className={inputClass} aria-label="Phrase to test" />
        <Button type="submit" disabled={!text.trim() || test.isPending}>{test.isPending ? <Spinner /> : 'Test'}</Button>
        <IconButton type="button" label="Test with an audio recording" onClick={() => fileRef.current?.click()}>
          {recognize.isPending ? <Spinner /> : <AudioLines size={17} />}
        </IconButton>
        <input ref={fileRef} type="file" accept="audio/*,.wav,.mp3,.ogg,.webm,.m4a" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) recognize.mutate(f); e.target.value = '' }} />
      </form>
      {error && <p className="text-[13px] text-danger">{error}</p>}
      <OutcomeView outcome={outcome} />
      {recognition && (
        recognition.rejected
          ? <p className="rounded-lg bg-sunken px-3 py-2.5 text-[13px] text-ink-muted">Heard “{recognition.transcript}”, ignored ({recognition.rejected}).</p>
          : <OutcomeView outcome={recognition.outcome} transcript={recognition.transcript}
              extra={`Recognized by ${recognition.engine} in ${Math.round(recognition.asr_ms)} ms.`} />
      )}
    </div>
  )
}

// --------------------------------------------------------------------- phrases editor

function PhraseEditor({ phrases, onSave, onCancel }: { phrases: string[]; onSave: (p: string[]) => void; onCancel: () => void }) {
  const [items, setItems] = useState(phrases)
  const [draft, setDraft] = useState('')
  const add = () => {
    const p = draft.trim()
    if (p && !items.some((x) => x.toLowerCase() === p.toLowerCase())) setItems([...items, p])
    setDraft('')
  }
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-1.5">
        {items.map((p) => (
          <span key={p} className="inline-flex items-center gap-1 rounded-full bg-sunken py-0.5 pr-1 pl-2.5 text-[12.5px] text-ink">
            {p}
            <button aria-label={`Remove ${p}`} onClick={() => setItems(items.filter((x) => x !== p))} className="rounded-full p-0.5 text-ink-faint hover:bg-line hover:text-ink">
              <X size={12} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder="Add a phrase and press Enter" className={inputClass} />
        <Button size="sm" onClick={add} disabled={!draft.trim()}>Add</Button>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" variant="primary" disabled={!items.length} onClick={() => onSave(items)}>Save phrases</Button>
      </div>
    </div>
  )
}

function CommandRow({ c, lang }: { c: CommandInfo; lang: Lang }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const refresh = () => void qc.invalidateQueries({ queryKey: ['commands'] })
  const update = useMutation({ mutationFn: (patch: Parameters<typeof api.updateCommand>[1]) => api.updateCommand(c.id, patch), onSuccess: () => { setEditing(false); refresh() } })
  const reset = useMutation({ mutationFn: () => api.resetCommand(c.id), onSuccess: refresh })
  const phrases = c.phrases[lang] ?? []
  return (
    <li className={cx('grid gap-2 px-4 py-3', !c.enabled && 'opacity-60')}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-medium text-ink">{c.title}{c.needs_llm && <span className="ml-2 text-[11.5px] font-normal text-ink-faint">uses the assistant</span>}</p>
          <p className="text-[12.5px] text-ink-muted">{c.description}</p>
        </div>
        {c.customized && c.builtin && (
          <IconButton size="sm" label="Restore the default phrases" onClick={() => reset.mutate()}><RotateCcw size={14} /></IconButton>
        )}
        <IconButton size="sm" label="Edit phrases" onClick={() => setEditing(!editing)}><Pencil size={14} /></IconButton>
        <div className="pt-1">
          <Switch hideLabel label={`${c.title} enabled`} checked={c.enabled} onChange={(enabled) => update.mutate({ enabled })} />
        </div>
      </div>
      {editing ? (
        <PhraseEditor phrases={phrases} onCancel={() => setEditing(false)} onSave={(p) => update.mutate({ phrases: { [lang]: p } })} />
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {phrases.length ? phrases.map((p) => (
            <span key={p} className="rounded-full border border-line px-2.5 py-0.5 text-[12.5px] text-ink">
              {p.split(/(\{\w+\})/).map((part, i) => (/^\{\w+\}$/.test(part) ? <em key={i} className="text-accent not-italic">{part.slice(1, -1)}</em> : part))}
            </span>
          )) : <span className="text-[12.5px] text-ink-faint">No phrases in this language</span>}
        </div>
      )}
    </li>
  )
}

// --------------------------------------------------------------------- custom builder

function CustomBuilder({ open, onClose, lang, existing }: { open: boolean; onClose: () => void; lang: Lang; existing?: CommandInfo }) {
  const qc = useQueryClient()
  const { data: cmds } = useCommands()
  const { data: voices = [] } = useVoices()
  const [name, setName] = useState(existing?.title ?? '')
  const [phrases, setPhrases] = useState((existing?.phrases[lang] ?? []).join('\n'))
  const [reply, setReply] = useState(existing?.reply ?? '')
  const [steps, setSteps] = useState<CustomCommandIn['steps']>(existing?.steps.length ? existing.steps : [{ action: 'set_speed', value: 1.2 }])
  const actions = cmds?.macro_actions ?? []
  const save = useMutation({
    mutationFn: () => {
      const body: CustomCommandIn = {
        name: name.trim(), reply: reply.trim(), enabled: true, steps,
        phrases: { ...(existing?.phrases ?? {}), [lang]: phrases.split('\n').map((p) => p.trim()).filter(Boolean) },
      }
      return existing ? api.updateCustom(existing.id.replace('custom:', ''), body) : api.createCustom(body)
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['commands'] }); onClose() },
  })
  const param = (action: string) => actions.find((a) => a.action === action)?.param ?? null
  return (
    <Modal open={open} onOpenChange={(o) => !o && onClose()} title={existing ? 'Edit command' : 'New voice command'}>
      <form className="grid gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
        <label className="grid gap-1.5">
          <span className="text-[13px] text-ink">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Study mode" className={inputClass} required />
        </label>
        <label className="grid gap-1.5">
          <span className="text-[13px] text-ink">Phrases in {LANGUAGES.find((l) => l.value === lang)?.label}, one per line</span>
          <textarea value={phrases} onChange={(e) => setPhrases(e.target.value)} rows={3} placeholder={'study mode\nlet’s study'}
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none" required />
        </label>
        <div className="grid gap-2">
          <span className="text-[13px] text-ink">Then do, in order</span>
          {steps.map((st, i) => (
            <div key={i} className="flex gap-2">
              <select value={st.action} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { action: e.target.value, value: param(e.target.value) === 'voice' ? voices[0]?.id ?? '' : param(e.target.value) ? 1 : null } : x)))}
                className="h-9 flex-1 rounded-lg border border-line bg-surface px-2 text-sm text-ink">
                {actions.map((a) => <option key={a.action} value={a.action}>{ACTION_LABELS[a.action] ?? a.action}</option>)}
              </select>
              {param(st.action) === 'voice' ? (
                <select value={String(st.value ?? '')} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                  className="h-9 w-36 rounded-lg border border-line bg-surface px-2 text-sm text-ink">
                  {voices.filter((v) => v.featured).map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              ) : param(st.action) ? (
                <input value={String(st.value ?? '')} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, value: param(st.action) === 'text' ? e.target.value : Number(e.target.value) } : x)))}
                  className={cx(inputClass, 'w-36')} aria-label="Value" />
              ) : null}
              <IconButton type="button" label="Remove step" onClick={() => setSteps(steps.filter((_, j) => j !== i))} disabled={steps.length === 1}><Trash2 size={15} /></IconButton>
            </div>
          ))}
          <Button type="button" size="sm" variant="ghost" className="justify-self-start" onClick={() => setSteps([...steps, { action: 'play', value: null }])} disabled={steps.length >= 10}>
            <Plus size={14} /> Add a step
          </Button>
        </div>
        <label className="grid gap-1.5">
          <span className="text-[13px] text-ink">Spoken reply (optional)</span>
          <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Study mode on" className={inputClass} />
        </label>
        {save.error && <p className="text-[13px] text-danger">{(save.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={save.isPending || !name.trim() || !phrases.trim()}>{existing ? 'Save' : 'Create command'}</Button>
        </div>
      </form>
    </Modal>
  )
}

function CustomRow({ c, lang }: { c: CommandInfo; lang: Lang }) {
  const qc = useQueryClient()
  const [edit, setEdit] = useState(false)
  const remove = useMutation({ mutationFn: () => api.deleteCustom(c.id.replace('custom:', '')), onSuccess: () => void qc.invalidateQueries({ queryKey: ['commands'] }) })
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium text-ink">{c.title}</p>
        <p className="text-[12.5px] text-ink-muted">
          {(c.phrases[lang] ?? []).map((p) => `“${p}”`).join(', ') || 'No phrases in this language'}
          {' → '}
          {c.steps.map((s) => `${ACTION_LABELS[s.action] ?? s.action}${s.value !== null && s.value !== '' ? ` ${s.value}` : ''}`).join(', then ')}
        </p>
      </div>
      <IconButton size="sm" label="Edit" onClick={() => setEdit(true)}><Pencil size={14} /></IconButton>
      <IconButton size="sm" label="Delete" onClick={() => remove.mutate()}><Trash2 size={14} /></IconButton>
      {edit && <CustomBuilder open={edit} onClose={() => setEdit(false)} lang={lang} existing={c} />}
    </li>
  )
}

// --------------------------------------------------------------------- tab

export function CommandsTab() {
  const { data, isLoading } = useCommands()
  const listenLang = useSettings((s) => s.profile.listening.language)
  const [lang, setLang] = useState<Lang>(listenLang)
  const [creating, setCreating] = useState(false)
  const commands = data?.commands ?? []
  const categories = (['playback', 'navigation', 'voice', 'assistant', 'app'] as const).map((cat) => [cat, commands.filter((c) => c.category === cat)] as const)
  const custom = commands.filter((c) => c.category === 'custom')

  return (
    <TabBody
      title="Voice commands"
      intro="The operations Lector reacts to. Switch any of them off, change what you say for them in each language, or add your own that chain several actions. Parts in blue are filled in by what you say."
    >
      <Segmented label="Phrases for" value={lang} onChange={setLang} options={LANGUAGES} />
      <Tester lang={lang} />
      {isLoading && <p className="text-[13px] text-ink-muted">Loading…</p>}

      <Group title={CATEGORY_TITLES.custom}>
        {custom.length > 0 && (
          <ul className="grid divide-y divide-line rounded-xl border border-line bg-surface">
            {custom.map((c) => <CustomRow key={c.id} c={c} lang={lang} />)}
          </ul>
        )}
        <Button variant="secondary" className="justify-self-start" onClick={() => setCreating(true)}><Plus size={15} /> New command</Button>
        {creating && <CustomBuilder open={creating} onClose={() => setCreating(false)} lang={lang} />}
      </Group>

      {categories.map(([cat, items]) => items.length > 0 && (
        <Group key={cat} title={CATEGORY_TITLES[cat]}>
          <ul className="grid divide-y divide-line rounded-xl border border-line bg-surface">
            {items.map((c) => <CommandRow key={c.id} c={c} lang={lang} />)}
          </ul>
        </Group>
      ))}
    </TabBody>
  )
}
