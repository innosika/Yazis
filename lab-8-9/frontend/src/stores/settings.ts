import { create } from 'zustand'

import { api } from '@/lib/api'
import type { ListeningSettings, Profile, ReadingSettings, VoiceSettings } from '@/lib/types'

export const DEFAULT_PROFILE: Profile = {
  voice: {
    voice: 'af_heart', blend: null, mix: 0.3, speed: 1, pitch: 0, volume: 1,
    sentence_pause: 0.12, paragraph_pause: 0.5,
  },
  reading: { citations: 'skip', urls: 'domain', math: 'verbalize', acronyms: 'auto', announce_headings: true },
  listening: {
    engine: 'auto', language: 'en', mode: 'push-to-talk', sensitivity: 0.5, confirmations: 'sound',
    llm_fallback: true, system_notifications: false,
  },
}

interface SettingsState {
  profile: Profile
  loaded: boolean
  load: () => Promise<void>
  setVoice: (patch: Partial<VoiceSettings>) => void
  setReading: (patch: Partial<ReadingSettings>) => void
  setListening: (patch: Partial<ListeningSettings>) => void
}

let saveTimer: number | undefined

function scheduleSave(profile: Profile): void {
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => {
    void api.saveSettings(profile).catch(() => undefined)
  }, 400)
}

export const useSettings = create<SettingsState>((set, get) => ({
  profile: DEFAULT_PROFILE,
  loaded: false,
  load: async () => {
    try {
      const profile = await api.settings()
      set({ profile, loaded: true })
    } catch {
      set({ loaded: true })
    }
  },
  setVoice: (patch) => {
    const profile = { ...get().profile, voice: { ...get().profile.voice, ...patch } }
    set({ profile })
    scheduleSave(profile)
  },
  setReading: (patch) => {
    const profile = { ...get().profile, reading: { ...get().profile.reading, ...patch } }
    set({ profile })
    scheduleSave(profile)
  },
  setListening: (patch) => {
    const profile = { ...get().profile, listening: { ...get().profile.listening, ...patch } }
    set({ profile })
    scheduleSave(profile)
  },
}))
