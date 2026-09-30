import { Command, Menu, Moon, Settings2, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

import { IconButton, Kbd, Tip } from '@/components/ui/primitives'
import { navigate } from '@/lib/router'
import { currentTheme, setTheme, type Theme } from '@/lib/theme'
import { useUi } from '@/stores/ui'

import { Wordmark } from './Wordmark'

export function TopBar() {
  const [theme, setThemeState] = useState<Theme>(currentTheme())
  const ui = useUi()

  useEffect(() => {
    const on = (e: Event) => setThemeState((e as CustomEvent<Theme>).detail)
    window.addEventListener('lector-theme', on)
    return () => window.removeEventListener('lector-theme', on)
  }, [])

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-paper/85 px-3 backdrop-blur-md sm:px-5">
      <IconButton label="Library" className="lg:hidden" onClick={() => ui.setLibrary(true)}>
        <Menu size={18} />
      </IconButton>
      <button onClick={() => navigate({ name: 'home' })} className="rounded-md px-1" aria-label="Lector, go to the library">
        <Wordmark />
      </button>
      <div className="flex-1" />
      <Tip label={<span className="flex items-center gap-1.5">Commands <Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>}>
        <button
          onClick={() => ui.setPalette(true)}
          className="hidden h-8 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-ink-muted hover:border-line-strong hover:text-ink sm:flex"
        >
          <Command size={14} />
          <span>Search actions</span>
          <Kbd>Ctrl K</Kbd>
        </button>
      </Tip>
      <IconButton label={theme === 'dark' ? 'Light mode' : 'Dark mode'} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
        {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
      </IconButton>
      <IconButton label="Settings" onClick={() => ui.openSettings()}>
        <Settings2 size={18} />
      </IconButton>
    </header>
  )
}
