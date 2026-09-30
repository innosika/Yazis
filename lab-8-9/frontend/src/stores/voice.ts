import { create } from 'zustand'

export type MicState = 'off' | 'starting' | 'listening' | 'hearing' | 'recognizing' | 'error'

export interface HudMessage {
  id: number
  tone: 'neutral' | 'success' | 'warning' | 'error'
  text: string
  detail?: string
}

export interface ActivityEvent {
  id: number
  at: number
  transcript: string
  command: string | null
  title: string | null
  method: string | null
  confidence: number | null
  engine: string
  asrMs: number
  matchMs: number
  rejected: string | null
  notes: string[]
  result: string
}

interface VoiceState {
  mic: MicState
  micError: string | null
  holding: boolean // push-to-talk key or button held
  hud: HudMessage | null
  activity: ActivityEvent[]
  setMic: (mic: MicState, error?: string | null) => void
  setHolding: (holding: boolean) => void
  showHud: (msg: Omit<HudMessage, 'id'>, ttlMs?: number) => void
  clearHud: () => void
  log: (event: Omit<ActivityEvent, 'id' | 'at'>) => void
  clearActivity: () => void
}

let hudTimer = 0
let seq = 1

function loadActivity(): ActivityEvent[] {
  try {
    return JSON.parse(localStorage.getItem('lector-activity') ?? '[]') as ActivityEvent[]
  } catch {
    return []
  }
}

export const useVoice = create<VoiceState>((set, get) => ({
  mic: 'off',
  micError: null,
  holding: false,
  hud: null,
  activity: loadActivity(),
  setMic: (mic, error = null) => set({ mic, micError: error }),
  setHolding: (holding) => set({ holding }),
  showHud: (msg, ttlMs = 3200) => {
    window.clearTimeout(hudTimer)
    set({ hud: { ...msg, id: seq++ } })
    if (ttlMs > 0) hudTimer = window.setTimeout(() => set({ hud: null }), ttlMs)
  },
  clearHud: () => set({ hud: null }),
  log: (event) => {
    const activity = [{ ...event, id: seq++, at: Date.now() }, ...get().activity].slice(0, 100)
    set({ activity })
    try {
      localStorage.setItem('lector-activity', JSON.stringify(activity))
    } catch {
      /* storage full or disabled */
    }
  },
  clearActivity: () => {
    set({ activity: [] })
    try {
      localStorage.removeItem('lector-activity')
    } catch {
      /* ignore */
    }
  },
}))

// Microphone level is pushed straight to subscribers (the orb), not through React state.
type LevelListener = (level: number) => void
const levelListeners = new Set<LevelListener>()
export const micLevel = {
  emit: (level: number) => levelListeners.forEach((l) => l(level)),
  subscribe: (l: LevelListener): (() => void) => {
    levelListeners.add(l)
    return () => {
      levelListeners.delete(l)
    }
  },
}
