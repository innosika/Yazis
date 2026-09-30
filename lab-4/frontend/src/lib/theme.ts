/** Light/dark preference: the OS decides until the user says otherwise. */

import { useEffect, useState } from 'react'

const KEY = 'mt-theme'
export type Theme = 'light' | 'dark'

function initial(): Theme {
  const stored = localStorage.getItem(KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initial)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(KEY, theme)
  }, [theme])

  return [theme, () => setTheme((value) => (value === 'dark' ? 'light' : 'dark'))]
}
