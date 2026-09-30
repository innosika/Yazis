/** Typed access to the API. One place that knows about URLs, errors and downloads. */

import type {
  Entry,
  EntryPage,
  MemoryMatch,
  MemoryStats,
  MemoryUnit,
  MemoryUnitPage,
  Meta,
  OovPage,
  Override,
  Rules,
  Sample,
  ScanResult,
  Suggestion,
  Tagsets,
  TranslateResult,
  DocumentSummary,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  if (!response.ok) {
    throw new ApiError(response.status, await describe(response))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

/** Turn FastAPI's error bodies into one sentence a user can act on. */
async function describe(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
          return field ? `${field}: ${item.msg}` : (item.msg ?? 'invalid value')
        })
        .join('; ')
    }
  } catch {
    /* fall through to the status line */
  }
  return `${response.status} ${response.statusText}`
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export interface TranslateInput {
  text: string
  domain: string
  mode: string
  include_direct?: boolean
  use_memory?: boolean
  save?: boolean
  title?: string
}

export const api = {
  meta: () => request<Meta>('/meta'),
  tagsets: () => request<Tagsets>('/meta/tagsets'),
  rules: () => request<Rules>('/meta/rules'),
  samples: () => request<Sample[]>('/translate/samples'),

  translate: (input: TranslateInput) => request<TranslateResult>('/translate', json(input)),

  /** The Unicode `.txt` export. Returns the text so the caller can also preview it. */
  async exportTxt(input: TranslateInput): Promise<{ filename: string; content: string }> {
    const response = await fetch(`${BASE}/export/txt`, {
      ...json(input),
      headers: { 'Content-Type': 'application/json' },
    })
    if (!response.ok) throw new ApiError(response.status, await describe(response))
    const disposition = response.headers.get('content-disposition') ?? ''
    const match = /filename="([^"]+)"/.exec(disposition)
    return { filename: match?.[1] ?? 'translation.txt', content: await response.text() }
  },

  documents: () => request<DocumentSummary[]>('/export/documents'),
  document: (id: number) =>
    request<{ id: number; title: string; source_text: string; domain_code: string; mode: string }>(
      `/export/documents/${id}`,
    ),

  dictionary: {
    search: (params: { q?: string; pos?: string; only_user?: boolean; page?: number }) => {
      const query = new URLSearchParams()
      if (params.q) query.set('q', params.q)
      if (params.pos) query.set('pos', params.pos)
      if (params.only_user) query.set('only_user', 'true')
      query.set('page', String(params.page ?? 1))
      return request<EntryPage>(`/dictionary/entries?${query}`)
    },
    entry: (id: number) => request<Entry>(`/dictionary/entries/${id}`),
    create: (body: {
      headword: string
      pos: string
      senses: { gloss: string; labels: string[]; translations: string[] }[]
    }) => request<Entry>('/dictionary/entries', json(body)),
    patchEntry: (id: number, body: { headword?: string; pos?: string }) =>
      request<Entry>(`/dictionary/entries/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    remove: (id: number) => request<void>(`/dictionary/entries/${id}`, { method: 'DELETE' }),
    addSense: (id: number, body: { gloss: string; labels: string[]; translations: string[] }) =>
      request<Entry>(`/dictionary/entries/${id}/senses`, json(body)),
    patchSense: (id: number, body: { gloss?: string; labels?: string[] }) =>
      request<Entry>(`/dictionary/senses/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    removeSense: (id: number) => request<Entry>(`/dictionary/senses/${id}`, { method: 'DELETE' }),
    setTranslations: (senseId: number, forms: string[]) =>
      request<Entry>(`/dictionary/senses/${senseId}/translations`, {
        method: 'PUT',
        body: JSON.stringify({ forms }),
      }),

    oov: (status = 'pending') => request<OovPage>(`/dictionary/oov?status=${status}`),
    fillSuggestions: () => request<OovPage>('/dictionary/oov/suggest', { method: 'POST' }),
    suggest: (lemma: string, upos = 'NOUN') =>
      request<Suggestion>(
        `/dictionary/suggest?lemma=${encodeURIComponent(lemma)}&upos=${upos}`,
      ),
    scan: (text: string, domain: string) =>
      request<ScanResult>('/dictionary/scan', json({ text, domain })),
    accept: (id: number, forms: string[], gloss = '') =>
      request<Entry>(`/dictionary/oov/${id}/accept`, json({ forms, gloss })),
    dismiss: (id: number) => request<void>(`/dictionary/oov/${id}/dismiss`, { method: 'POST' }),

    overrides: () => request<Override[]>('/dictionary/overrides'),
    lockSense: (body: {
      headword: string
      pos: string
      domain_code: string
      sense_id: number
      translation_id: number | null
      note?: string
    }) => request<void>('/dictionary/overrides', json(body)),
    unlockSense: (id: number) =>
      request<void>(`/dictionary/overrides/${id}`, { method: 'DELETE' }),
  },

  memory: {
    list: (params: { q?: string; domain?: string; page?: number }) => {
      const query = new URLSearchParams()
      if (params.q) query.set('q', params.q)
      if (params.domain) query.set('domain', params.domain)
      query.set('page', String(params.page ?? 1))
      return request<MemoryUnitPage>(`/memory/units?${query}`)
    },
    save: (body: { source_text: string; target_text: string; domain_code: string }) =>
      request<MemoryUnit>('/memory/units', json(body)),
    remove: (id: number) => request<void>(`/memory/units/${id}`, { method: 'DELETE' }),
    search: (text: string, domain: string) =>
      request<MemoryMatch[]>('/memory/search', json({ text, domain })),
    stats: () => request<MemoryStats>('/memory/stats'),
    exportAll: () => request<MemoryUnit[]>('/memory/export'),
    importUnits: (units: { source_text: string; target_text: string; domain_code: string }[]) =>
      request<MemoryStats>('/memory/import', json({ units })),
  },
}

/** Hand the browser a file without a server round trip. */
export function downloadText(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
