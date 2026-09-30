import type {
  CommandInfo,
  CommandsResponse,
  DocumentFull,
  DocumentSummary,
  Health,
  Lang,
  LexiconEntry,
  MatchOutcome,
  Profile,
  ReadingSettings,
  Recognition,
  Synthesis,
  VoiceInfo,
  VoiceStatus,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, init)
  } catch {
    throw new ApiError(0, 'Lector’s server is not reachable. Is `make up` running?')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const body = text ? safeJson(text) : null
  if (!res.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail: unknown }).detail : null
    const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? 'The request was not valid.' : res.statusText
    throw new ApiError(res.status, message || `Request failed (${res.status})`)
  }
  return body as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function json(method: string, body: unknown, signal?: AbortSignal): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal }
}

export interface SynthesizeParams {
  text: string
  kind: 'text' | 'heading'
  voice: { id: string; blend: string | null; mix: number }
  speed: number
  pitch: number
  options: ReadingSettings
  priority: 'now' | 'prefetch' | 'background'
}

export const api = {
  health: () => request<Health>('/health/ready'),
  voices: () => request<VoiceInfo[]>('/tts/voices'),
  synthesize: (p: SynthesizeParams, signal?: AbortSignal) => request<Synthesis>('/tts/synthesize', json('POST', p, signal)),
  spokenForm: (texts: string[], options: ReadingSettings, kind: 'text' | 'heading' = 'text') =>
    request<{ spoken: string[] }>('/tts/normalize', json('POST', { texts, options, kind })),
  segment: (text: string) =>
    request<{ units: { start: number; end: number; paragraph: number }[] }>('/tts/segment', json('POST', { text })),

  documents: () => request<DocumentSummary[]>('/documents'),
  document: (id: string) => request<DocumentFull>(`/documents/${id}`),
  createFromText: (text: string, title?: string) => request<DocumentFull>('/documents/text', json('POST', { text, title })),
  importSource: (source: string) => request<DocumentFull>('/documents/import', json('POST', { source })),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentFull>('/documents/upload', { method: 'POST', body: form })
  },
  savePosition: (id: string, block: number, sentence: number, progress: number) =>
    request<DocumentSummary>(`/documents/${id}/position`, json('PATCH', { block, sentence, progress })),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  documentSource: (id: string) => request<{ title: string; authors: string[]; text: string }>(`/documents/${id}/source`),
  updateDocument: (id: string, patch: { title?: string; authors?: string[]; text?: string }) =>
    request<DocumentFull>(`/documents/${id}`, json('PATCH', patch)),

  settings: () => request<Profile>('/settings'),
  saveSettings: (p: Profile) => request<Profile>('/settings', json('PUT', p)),

  lexicon: () => request<{ entries: LexiconEntry[]; builtin: number }>('/lexicon'),
  addLexicon: (term: string, say_as: string) => request<LexiconEntry>('/lexicon', json('POST', { term, say_as })),
  deleteLexicon: (id: number) => request<void>(`/lexicon/${id}`, { method: 'DELETE' }),

  commands: () => request<CommandsResponse>('/commands'),
  testCommand: (text: string, language: Lang, document_id?: string | null, llm_fallback = true) =>
    request<MatchOutcome>('/commands/test', json('POST', { text, language, document_id, llm_fallback })),
  updateCommand: (id: string, patch: { enabled?: boolean; phrases?: Partial<Record<Lang, string[]>> }) =>
    request<CommandInfo>(`/commands/${id}`, json('PUT', patch)),
  resetCommand: (id: string) => request<void>(`/commands/${id}/override`, { method: 'DELETE' }),
  createCustom: (c: CustomCommandIn) => request<CommandInfo>('/commands/custom', json('POST', c)),
  updateCustom: (id: string, c: CustomCommandIn) => request<CommandInfo>(`/commands/custom/${id}`, json('PUT', c)),
  deleteCustom: (id: string) => request<void>(`/commands/custom/${id}`, { method: 'DELETE' }),

  voiceStatus: () => request<VoiceStatus>('/voice/status'),
  recognize: (wav: Blob, fields: RecognizeFields) => {
    const form = new FormData()
    form.append('audio', wav, 'utterance.wav')
    for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) form.append(k, String(v))
    return request<Recognition>('/voice/recognize', { method: 'POST', body: form })
  },

  explain: (term: string, context: string, title: string) =>
    request<{ text: string }>('/assist/explain', json('POST', { term, context, title })),
  summarize: (text: string, title: string, section: string) =>
    request<{ text: string }>('/assist/summarize', json('POST', { text, title, section })),
}

export interface CustomCommandIn {
  name: string
  phrases: Partial<Record<Lang, string[]>>
  steps: { action: string; value: string | number | null }[]
  reply: string
  enabled: boolean
}

export interface RecognizeFields {
  language: Lang
  mode: 'command' | 'dictation'
  engine: 'auto' | 'cloud' | 'local'
  playing: boolean
  played_text: string
  document_id: string | null
  llm_fallback: boolean
}
