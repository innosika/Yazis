export type Lang = 'en' | 'ru' | 'de' | 'fr'

export interface VoiceInfo {
  id: string
  name: string
  accent: 'us' | 'gb'
  gender: 'female' | 'male'
  grade: string
  featured: boolean
}

export interface VoiceSettings {
  voice: string
  blend: string | null
  mix: number
  speed: number
  pitch: number
  volume: number
  sentence_pause: number
  paragraph_pause: number
}

export interface ReadingSettings {
  citations: 'skip' | 'read'
  urls: 'skip' | 'link' | 'domain'
  math: 'verbalize' | 'skip'
  acronyms: 'auto' | 'spell'
  announce_headings: boolean
}

export interface ListeningSettings {
  engine: 'auto' | 'cloud' | 'local'
  language: Lang
  mode: 'hands-free' | 'push-to-talk'
  sensitivity: number
  confirmations: 'voice' | 'sound' | 'off'
  llm_fallback: boolean
  system_notifications: boolean
}

export interface Profile {
  voice: VoiceSettings
  reading: ReadingSettings
  listening: ListeningSettings
}

export interface Sentence {
  start: number
  end: number
  units: [number, number][]
}

export interface Block {
  id: string
  kind: 'heading' | 'paragraph' | 'item' | 'equation'
  level: number
  text: string
  sentences: Sentence[]
  math: [number, number][]
}

export interface SectionRef {
  title: string
  block: number
  level: number
}

export interface DocumentSummary {
  id: string
  title: string
  authors: string[]
  source: { kind?: string; id?: string; url?: string; filename?: string }
  word_count: number
  minutes: number
  progress: number
  sections: number
  created_at: string
  opened_at: string
}

export interface DocumentFull extends DocumentSummary {
  structure: { blocks: Block[]; sections: SectionRef[]; word_count: number }
  position: { block?: number; sentence?: number }
}

export interface Word {
  text: string
  start: number
  end: number
  src_start: number
  src_end: number
}

export interface Synthesis {
  id: string
  audio_url: string
  duration: number
  spoken: string
  words: Word[]
  cached: boolean
  compute_ms: number
}

export interface MatchInfo {
  command: string
  title: string
  phrase: string
  method: 'template' | 'fuzzy' | 'llm'
  confidence: number
  slots: Record<string, string | number>
  alternatives: { command: string; title: string; confidence: number }[]
  reply: string
  steps: { action: string; value: string | number | null }[]
  builtin: boolean
}

export interface MatchOutcome {
  utterance: string
  normalized: string
  match: MatchInfo | null
  suggestions: { command: string; title: string; phrase: string; confidence: number }[]
  stages: string[]
  match_ms: number
}

export interface Recognition {
  transcript: string
  engine: string
  language: string
  notes: string[]
  asr_ms: number
  audio_s: number
  rejected: string | null
  echo_ratio: number
  outcome: MatchOutcome | null
}

export interface CommandInfo {
  id: string
  title: string
  category: 'playback' | 'navigation' | 'voice' | 'assistant' | 'app' | 'custom'
  description: string
  enabled: boolean
  builtin: boolean
  customized: boolean
  slots: string[]
  needs_llm: boolean
  phrases: Record<Lang, string[]>
  reply: string
  steps: { action: string; value: string | number | null }[]
}

export interface CommandsResponse {
  commands: CommandInfo[]
  languages: Lang[]
  macro_actions: { action: string; param: string | null }[]
}

export interface Health {
  status: string
  tts: string
  asr_local: string
  groq: 'configured' | 'missing'
}

export interface VoiceStatus {
  cloud: string | null
  local: string | null
  cloud_available: boolean
  cloud_cooldown_s: number
  cloud_issue: string | null
  local_status: string
  llm: boolean
}

export interface LexiconEntry {
  id: number
  term: string
  say_as: string
}
