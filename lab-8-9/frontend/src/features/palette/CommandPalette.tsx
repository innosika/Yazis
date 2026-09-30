import { Command } from 'cmdk'
import { Dialog as RDialog } from 'radix-ui'

import { plainText } from '@/lib/format'
import { useCommands, useDocuments } from '@/lib/queries'
import { navigate } from '@/lib/router'
import { usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'
import { runCommand, showResult } from '@/voice/actions'

const HIDDEN = new Set(['explain', 'switch_voice', 'set_speed', 'go_to_section'])

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen)
  const setOpen = useUi((s) => s.setPalette)
  const { data: commands } = useCommands()
  const { data: docs } = useDocuments()
  const doc = usePlayer((s) => s.doc)
  const lang = useSettings((s) => s.profile.listening.language)

  const run = async (id: string, slots: Record<string, string | number> = {}, steps: { action: string; value: string | number | null }[] = []) => {
    setOpen(false)
    const wasPlaying = ['playing', 'loading'].includes(usePlayer.getState().status)
    showResult(await runCommand(id, slots, { wasPlaying, source: 'palette' }, steps))
  }

  const item = 'flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2 text-[13.5px] text-ink data-[selected=true]:bg-accent-soft'
  const group = 'px-1 py-1 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[12px] [&_[cmdk-group-heading]]:text-ink-muted'

  return (
    <RDialog.Root open={open} onOpenChange={setOpen}>
      <RDialog.Portal>
        <RDialog.Overlay className="fade-in fixed inset-0 z-50 bg-ink/25 dark:bg-black/60" />
        <RDialog.Content aria-describedby={undefined} className="fade-in fixed top-[14vh] left-1/2 z-50 w-[min(600px,calc(100vw-24px))] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-surface shadow-float">
          <RDialog.Title className="sr-only">Actions</RDialog.Title>
          <Command label="Actions" loop>
            <Command.Input autoFocus placeholder="Type an action, a section or a document…" className="h-12 w-full border-b border-line bg-transparent px-4 text-[15px] text-ink placeholder:text-ink-faint focus:outline-none" />
            <Command.List className="scroll-thin max-h-[55vh] overflow-y-auto p-1">
              <Command.Empty className="px-4 py-6 text-[13px] text-ink-muted">Nothing matches.</Command.Empty>
              {doc && doc.structure.sections.length > 1 && (
                <Command.Group heading="Go to section" className={group}>
                  {doc.structure.sections.map((s) => (
                    <Command.Item key={s.block} value={`section ${s.title}`} className={item}
                      onSelect={() => void run('go_to_section', { section_block: s.block, section_title: s.title })}>
                      <span className="truncate">{s.title}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              <Command.Group heading="Actions" className={group}>
                {commands?.commands.filter((c) => c.enabled && !HIDDEN.has(c.id)).map((c) => (
                  <Command.Item key={c.id} value={`${c.title} ${c.phrases[lang]?.join(' ') ?? ''}`} className={item} onSelect={() => void run(c.id, {}, c.steps)}>
                    <span>{c.title}</span>
                    {c.phrases[lang]?.[0] && <span className="truncate text-[12.5px] text-ink-muted">say “{c.phrases[lang][0]}”</span>}
                  </Command.Item>
                ))}
              </Command.Group>
              {docs && docs.length > 0 && (
                <Command.Group heading="Open" className={group}>
                  {docs.slice(0, 12).map((d) => (
                    <Command.Item key={d.id} value={`open ${d.title}`} className={item} onSelect={() => { setOpen(false); navigate({ name: 'doc', id: d.id }) }}>
                      <span className="truncate font-serif">{plainText(d.title)}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </RDialog.Content>
      </RDialog.Portal>
    </RDialog.Root>
  )
}
