/** Shapes returned by the API. Kept in one place so a contract change breaks the build. */

export type DomainCode = 'general' | 'cs' | 'lit'
export type Mode = 'transfer' | 'direct'

export interface Domain {
  code: DomainCode
  title: string
  description: string
  label_count: number
  keyword_count: number
}

export interface ModeInfo {
  code: Mode
  title: string
  description: string
}

export interface DictionaryStats {
  entries: number
  senses: number
  translations: number
  user_entries: number
  user_translations: number
  multiword_units: number
  by_pos: Record<string, number>
}

export interface MemoryStats {
  units: number
  post_edited: number
  imported: number
  total_hits: number
  by_domain: Record<string, number>
}

export interface Meta {
  direction: { source: string; target: string; code: string }
  variant: number
  domains: Domain[]
  modes: ModeInfo[]
  dictionary: DictionaryStats
  memory: MemoryStats
  thresholds: { tm_exact: number; tm_fuzzy: number; max_input_chars: number }
  enrichment: { wiktionary_enabled: boolean }
}

export interface TagInfo {
  code: string
  name: string
  description: string
  examples: string
}

export interface Tagsets {
  upos: TagInfo[]
  penn: TagInfo[]
  opencorpora: TagInfo[]
  dependencies: { code: string; description: string }[]
}

export interface Rules {
  prepositions: { english: string; russian: string; case: string }[]
  compound_prepositions: { english: string; russian: string; case: string }[]
  dependency_cases: { dependency: string; case: string }[]
  register_penalties: { label: string; penalty: number }[]
}

export type PieceKind =
  | 'word'
  | 'punct'
  | 'function'
  | 'preposition'
  | 'auxiliary'
  | 'untranslated'
  | 'dropped'

export interface Piece {
  surface: string
  kind: PieceKind
  source_indices: number[]
  source_text: string
  lemma: string
  tag: string
  decoded: string[]
  case: string | null
  note: string
}

export interface MemoryMatch {
  id: number
  similarity: number
  source_text: string
  target_text: string
  domain_code: string
  origin: string
  exact: boolean
}

export interface Sentence {
  index: number
  source: string
  target: string
  pieces: Piece[]
  stages: Record<string, string>
  memory: MemoryMatch | null
  direct: string
}

export interface WordRow {
  lemma: string
  upos: string
  tag: string
  count: number
  forms: string[]
  translation: string
  translation_accented: string
  gloss: string
  sense_index: number
  sense_count: number
  translated: boolean
  pos_name: string
  pos_description: string
  tag_name: string
  tag_description: string
  features: string[]
  ambiguous: boolean
  from_user: boolean
  dropped_by_rule: boolean
  note: string
}

export interface TokenInfo {
  sentence: number
  index: number
  text: string
  lemma: string
  upos: string
  tag: string
  morph: string
  dep: string
  head: number
  translation: string
  translation_accented: string
  gloss: string
  sense_count: number
  ambiguous: boolean
  translated: boolean
  dropped_by_rule: boolean
  target_tag: string
  target_decoded: string[]
  note: string
  features: string[]
  pos_name: string
  tag_name: string
}

export interface TreeNode {
  id: number
  text: string
  lemma: string
  upos: string
  pos_name: string
  tag: string
  tag_name: string
  tag_description: string
  dep: string
  dep_description: string
  features: string[]
  translation: string
  target_decoded: string[]
  depth: number
  width: number
  children: TreeNode[]
}

export interface Tree {
  sentence: number
  text: string
  root: TreeNode | null
}

export interface Signal {
  name: string
  value: number
  weight: number
  contribution: number
  detail: string
}

export interface Candidate {
  sense_id: number
  translation_id: number | null
  entry_pos: string | null
  sense_index: number
  gloss: string
  labels: string[]
  translation: string
  translation_accented: string
  alternatives: string[]
  score: number
  signals: Signal[]
  selected: boolean
  locked: boolean
}

export interface Ambiguity {
  sentence: number
  token: number
  text: string
  lemma: string
  upos: string
  pos_name: string
  context: string
  margin: number
  candidates: Candidate[]
}

export interface Stats {
  characters: number
  sentences: number
  words: number
  content_words: number
  translated_words: number
  untranslated_words: number
  unique_lemmas: number
  coverage: number
  ambiguous_words: number
  dropped_tokens: number
  inserted_tokens: number
  pos_distribution: Record<string, number>
}

export interface OovMention {
  lemma: string
  upos: string
  occurrences: number
  context: string
}

export interface TranslateResult {
  document_id: number | null
  domain: DomainCode
  mode: Mode
  source: string
  target: string
  direct_target: string
  duration_ms: number
  stats: Stats
  sentences: Sentence[]
  words: WordRow[]
  tokens: TokenInfo[]
  trees: Tree[]
  ambiguities: Ambiguity[]
  oov: OovMention[]
  memory_hits: number
}

export interface Sample {
  name: string
  title: string
  domain: DomainCode
  characters: number
  text: string
}

export interface Translation {
  id: number
  idx: number
  form_accented: string
  form_plain: string
  is_user: boolean
}

export interface Sense {
  id: number
  idx: number
  gloss: string
  labels: string[]
  domain_scores: Record<string, number>
  translations: Translation[]
}

export interface Entry {
  id: number
  headword: string
  headword_norm: string
  pos: string | null
  ipa: string | null
  word_count: number
  source: string
  is_user: boolean
  senses: Sense[]
}

export interface EntryPage {
  total: number
  page: number
  per_page: number
  items: Entry[]
}

export interface Suggestion {
  lemma: string
  pos: string
  source: 'wiktionary' | 'derivation' | 'transcription'
  confidence: number
  forms: string[]
  explanation: string
}

export interface OovTerm {
  id: number
  lemma: string
  pos: string
  occurrences: number
  status: string
  suggestion: Suggestion | null
  context: string | null
  first_seen: string
  last_seen: string
}

export interface OovPage {
  total: number
  pending: number
  items: OovTerm[]
}

export interface ScanResult {
  scanned_words: number
  found: number
  suggestions: Suggestion[]
}

export interface Override {
  id: number
  headword_norm: string
  pos: string
  domain_code: string
  sense_id: number
  translation_id: number | null
  translation: string
  gloss: string
  note: string | null
  created_at: string
}

export interface MemoryUnit {
  id: number
  source_text: string
  target_text: string
  domain_code: string
  origin: string
  hits: number
  created_at: string
  updated_at: string
}

export interface MemoryUnitPage {
  total: number
  page: number
  per_page: number
  items: MemoryUnit[]
}

export interface DocumentSummary {
  id: number
  title: string
  domain_code: string
  mode: string
  stats: Stats
  duration_ms: number
  characters: number
  created_at: string
}
