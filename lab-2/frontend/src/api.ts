export type Lang = 'ru' | 'en'

export interface Detection {
  method: string
  lang: Lang
  confidence: number
  scores: Record<string, number>
  elapsed_ms: number
  details: Record<string, any>
}

export interface DetectResult {
  text_chars: number
  normalized_chars: number
  words: number
  results: Detection[]
  consensus: Lang | null
  agree: boolean
  text_preview?: string
  filename?: string
  transcript?: string
  whisper_language?: string | null
  duration?: number | null
}

export interface MethodInfo { id: string; title: string; short: string; description: string; metric: string }

export interface Info {
  languages: { code: Lang; name: string }[]
  methods: MethodInfo[]
  corpus: Record<Lang, { files: number; bytes: number; chars: number; words: number; titles: string[] }>
  fit_times_ms: Record<string, number>
  neural: Record<string, any>
  neural_history: { epoch: number; loss: number; val_acc: number }[]
  voice_available: boolean
}

export interface CollectionDoc { id: string; title: string; lang: Lang; source: string; chars: number; origin: string; url: string; group: 'standard' | 'hard'; note: string }

export interface Prediction { lang: Lang; correct: boolean; confidence: number; elapsed_ms: number; scores: Record<string, number> }
export interface EvalRow { id: string; title: string; true_lang: Lang; chars: number; source: string; origin: string; url: string; group: 'standard' | 'hard'; note: string; predictions: Record<string, Prediction> }
export interface GroupStat { accuracy: number; correct: number; total: number }
export interface MethodSummary { title: string; accuracy: number; correct: number; total: number; errors: number; avg_time_ms: number; total_time_ms: number; confusion: Record<string, Record<string, number>>; groups: Record<string, GroupStat> }
export interface Evaluation { documents: EvalRow[]; summary: Record<string, MethodSummary>; count: number; total_elapsed_ms: number; languages: Lang[] }

export interface CurvePoint { length: number; [method: string]: any }
export interface Curve { lengths: number[]; samples_per_doc: number; documents: number; points: CurvePoint[]; min_length_95: Record<string, number | null>; methods: Record<string, string> }

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Ошибка ${r.status}`
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  info: () => fetch('/api/info').then(r => handle<Info>(r)),
  detect: (text: string, is_html = false) =>
    fetch('/api/detect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, is_html }) }).then(r => handle<DetectResult>(r)),
  detectFile: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch('/api/detect/file', { method: 'POST', body: fd }).then(r => handle<DetectResult>(r))
  },
  collection: () => fetch('/api/collection').then(r => handle<{ count: number; documents: CollectionDoc[] }>(r)),
  upload: (file: File, lang: Lang) => {
    const fd = new FormData(); fd.append('file', file); fd.append('lang', lang)
    return fetch('/api/collection/upload', { method: 'POST', body: fd }).then(r => handle<CollectionDoc>(r))
  },
  remove: (id: string) => fetch(`/api/collection/${id}`, { method: 'DELETE' }).then(r => handle<{ deleted: string }>(r)),
  evaluate: () => fetch('/api/collection/evaluate', { method: 'POST' }).then(r => handle<Evaluation>(r)),
  curve: (lengths: number[], samples: number) =>
    fetch(`/api/learning-curve?lengths=${lengths.join(',')}&samples=${samples}`).then(r => handle<Curve>(r)),
  voice: (blob: Blob, filename: string) => {
    const fd = new FormData(); fd.append('file', blob, filename)
    return fetch('/api/voice', { method: 'POST', body: fd }).then(r => handle<DetectResult>(r))
  },
}

export const LANG_NAME: Record<string, string> = { ru: 'Русский', en: 'Английский' }
export const LANG_FLAG: Record<string, string> = { ru: '🇷🇺', en: '🇬🇧' }
export const METHOD_ORDER = ['ngram', 'alphabet', 'neural']
export const METHOD_COLOR: Record<string, string> = { ngram: '#2563eb', alphabet: '#d97706', neural: '#7c3aed' }
export const fmtMs = (ms: number) => ms < 1 ? `${ms.toFixed(3)} мс` : ms < 100 ? `${ms.toFixed(2)} мс` : `${ms.toFixed(0)} мс`
export const pct = (x: number) => `${(x * 100).toFixed(x === 1 || x === 0 ? 0 : 1)}%`
