import { create } from 'zustand'

export type SettingsTab = 'voice' | 'reading' | 'listening' | 'commands' | 'pronunciation'

export interface AssistantCard {
  kind: 'explain' | 'summary' | 'info'
  title: string
  text: string | null
  error: string | null
}

interface UiState {
  settingsOpen: boolean
  settingsTab: SettingsTab
  paletteOpen: boolean
  libraryOpen: boolean // narrow screens only
  spokenForm: boolean
  assistant: AssistantCard | null
  openSettings: (tab?: SettingsTab) => void
  closeSettings: () => void
  setPalette: (open: boolean) => void
  setLibrary: (open: boolean) => void
  setSpokenForm: (on: boolean) => void
  setAssistant: (card: AssistantCard | null) => void
}

export const useUi = create<UiState>((set) => ({
  settingsOpen: false,
  settingsTab: 'voice',
  paletteOpen: false,
  libraryOpen: false,
  spokenForm: false,
  assistant: null,
  openSettings: (tab) => set((s) => ({ settingsOpen: true, settingsTab: tab ?? s.settingsTab })),
  closeSettings: () => set({ settingsOpen: false }),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  setLibrary: (libraryOpen) => set({ libraryOpen }),
  setSpokenForm: (spokenForm) => set({ spokenForm }),
  setAssistant: (assistant) => set({ assistant }),
}))
