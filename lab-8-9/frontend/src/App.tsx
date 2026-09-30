import { useEffect } from 'react'
import { Toaster } from 'sonner'

import { TooltipProvider } from '@/components/ui/primitives'
import { useHotkeys } from '@/lib/hotkeys'
import { useHealth, useVoices } from '@/lib/queries'
import { useRoute } from '@/lib/router'
import { useSettings } from '@/stores/settings'
import { setVoiceList } from '@/voice/actions'

import { AssistantCard } from './features/assistant/AssistantCard'
import { TopBar } from './features/layout/TopBar'
import { LibraryRail } from './features/library/LibraryRail'
import { NewDocument } from './features/library/NewDocument'
import { CommandPalette } from './features/palette/CommandPalette'
import { Dock } from './features/player/Dock'
import { DocumentEditor } from './features/reader/DocumentEditor'
import { Reader } from './features/reader/Reader'
import { SettingsSheet } from './features/settings/SettingsSheet'

function Preparing() {
  const { data, error } = useHealth()
  if (data?.status === 'ready') return null
  const text = error
    ? 'Waiting for Lector’s server…'
    : data?.tts === 'error' ? 'The voice failed to load. Check `make logs`.' : 'Preparing the voice…'
  return (
    <div className="fixed top-16 left-1/2 z-40 -translate-x-1/2 rounded-full border border-line bg-surface px-4 py-1.5 text-[13px] text-ink-muted shadow-float" role="status">
      {text}
    </div>
  )
}

export function App() {
  const route = useRoute()
  const load = useSettings((s) => s.load)
  const { data: voices } = useVoices()
  useHotkeys()
  useEffect(() => void load(), [load])
  useEffect(() => {
    if (voices) setVoiceList(voices)
  }, [voices])

  return (
    <TooltipProvider>
      <div className="min-h-dvh bg-paper text-ink">
        <TopBar />
        <div className="flex">
          <LibraryRail />
          <main className="min-w-0 flex-1">
            {route.name === 'doc' ? (
              <Reader key={route.id} id={route.id} />
            ) : route.name === 'edit' ? (
              <DocumentEditor key={route.id} id={route.id} />
            ) : (
              <NewDocument showRecent={route.name === 'home'} />
            )}
          </main>
        </div>
        <Dock />
        <AssistantCard />
        <SettingsSheet />
        <CommandPalette />
        <Preparing />
        <Toaster position="top-center" />
      </div>
    </TooltipProvider>
  )
}
