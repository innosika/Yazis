import { Tabs } from 'radix-ui'
import { X } from 'lucide-react'

import { cx, DialogClose, IconButton, Sheet } from '@/components/ui/primitives'
import { useUi, type SettingsTab } from '@/stores/ui'

import { CommandsTab } from './CommandsTab'
import { ListeningTab } from './ListeningTab'
import { PronunciationTab } from './PronunciationTab'
import { ReadingTab } from './ReadingTab'
import { VoiceTab } from './VoiceTab'

const TABS: { id: SettingsTab; label: string; hint: string }[] = [
  { id: 'voice', label: 'Voice', hint: 'Who reads and how fast' },
  { id: 'reading', label: 'Reading', hint: 'Citations, formulas, links' },
  { id: 'listening', label: 'Listening', hint: 'Microphone and language' },
  { id: 'commands', label: 'Commands', hint: 'What you can say' },
  { id: 'pronunciation', label: 'Pronunciation', hint: 'Words said your way' },
]

export function SettingsSheet() {
  const { settingsOpen, settingsTab, closeSettings, openSettings } = useUi()
  return (
    <Sheet open={settingsOpen} onOpenChange={(o) => (o ? openSettings() : closeSettings())} title="Settings" width="max-w-[880px]">
      <Tabs.Root
        value={settingsTab}
        onValueChange={(v) => openSettings(v as SettingsTab)}
        orientation="vertical"
        className="flex h-full min-h-0 flex-col sm:flex-row"
      >
        <div className="flex shrink-0 flex-col border-line sm:w-56 sm:border-r">
          <div className="flex h-14 items-center justify-between px-5">
            <h2 className="text-[15px] font-semibold text-ink">Settings</h2>
            <DialogClose asChild>
              <IconButton label="Close settings" className="sm:hidden"><X size={18} /></IconButton>
            </DialogClose>
          </div>
          <Tabs.List aria-label="Settings sections" className="scroll-thin flex gap-1 overflow-x-auto px-3 pb-3 sm:flex-col sm:overflow-visible">
            {TABS.map((t) => (
              <Tabs.Trigger
                key={t.id}
                value={t.id}
                className={cx(
                  'grid shrink-0 rounded-lg px-3 py-2 text-left transition-colors',
                  'data-[state=active]:bg-accent-soft data-[state=inactive]:hover:bg-sunken',
                )}
              >
                <span className="text-[13.5px] font-medium text-ink">{t.label}</span>
                <span className="hidden text-[12px] text-ink-muted sm:block">{t.hint}</span>
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </div>
        <div className="relative min-h-0 flex-1">
          <div className="absolute top-3 right-3 z-10 hidden sm:block">
            <DialogClose asChild>
              <IconButton label="Close settings"><X size={18} /></IconButton>
            </DialogClose>
          </div>
          <div className="scroll-thin h-full overflow-y-auto">
            <Tabs.Content value="voice" className="outline-none"><VoiceTab /></Tabs.Content>
            <Tabs.Content value="reading" className="outline-none"><ReadingTab /></Tabs.Content>
            <Tabs.Content value="listening" className="outline-none"><ListeningTab /></Tabs.Content>
            <Tabs.Content value="commands" className="outline-none"><CommandsTab /></Tabs.Content>
            <Tabs.Content value="pronunciation" className="outline-none"><PronunciationTab /></Tabs.Content>
          </div>
        </div>
      </Tabs.Root>
    </Sheet>
  )
}

export function TabBody({ title, intro, children }: { title: string; intro?: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[600px] px-6 pt-6 pb-16 sm:pt-12">
      <h3 className="text-[17px] font-semibold text-ink">{title}</h3>
      {intro && <p className="mt-1 max-w-[60ch] text-[13.5px] leading-relaxed text-ink-muted">{intro}</p>}
      <div className="mt-6 grid gap-7">{children}</div>
    </div>
  )
}

export function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4">
      <h4 className="border-b border-line pb-2 text-[13px] font-semibold text-ink">{title}</h4>
      {children}
    </section>
  )
}
