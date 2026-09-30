import { useEffect } from 'react'

import { currentRoute, navigate } from '@/lib/router'
import { usePlayer } from '@/stores/player'
import { useSettings } from '@/stores/settings'
import { useUi } from '@/stores/ui'
import { useVoice } from '@/stores/voice'
import { runCommand, showResult } from '@/voice/actions'
import { startListening, stopListening, talkEnd, talkStart } from '@/voice/controller'

function typing(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null
  return Boolean(t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)))
}

export function useHotkeys(): void {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        useUi.getState().setPalette(!useUi.getState().paletteOpen)
        return
      }
      if (typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
      if (useUi.getState().paletteOpen || useUi.getState().settingsOpen) return
      const p = usePlayer.getState()
      const act = async (id: string) => showResult(await runCommand(id, {}, { wasPlaying: p.status === 'playing', source: 'keyboard' }))
      switch (e.key) {
        case ' ':
          e.preventDefault()
          void p.toggle()
          break
        case 'ArrowRight':
          e.preventDefault()
          void p.move(e.shiftKey ? 'paragraph' : 'sentence', 1)
          break
        case 'ArrowLeft':
          e.preventDefault()
          void p.move(e.shiftKey ? 'paragraph' : 'sentence', -1)
          break
        case ']':
          void act('faster')
          break
        case '[':
          void act('slower')
          break
        case 'm':
        case 'M': {
          if (e.repeat) return
          const { mode } = useSettings.getState().profile.listening
          if (mode === 'push-to-talk') void talkStart()
          else void (useVoice.getState().mic === 'off' ? startListening() : stopListening())
          break
        }
        case '?':
          useUi.getState().openSettings('commands')
          break
        case 'e':
        case 'E': {
          const route = currentRoute()
          if (route.name === 'doc') {
            e.preventDefault()
            navigate({ name: 'edit', id: route.id })
          }
          break
        }
      }
    }
    const up = (e: KeyboardEvent) => {
      if ((e.key === 'm' || e.key === 'M') && useSettings.getState().profile.listening.mode === 'push-to-talk') void talkEnd()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [])
}
