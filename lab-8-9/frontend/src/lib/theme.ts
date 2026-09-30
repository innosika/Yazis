export type Theme = 'light' | 'dark'

const KEY = 'lector-theme'

export function currentTheme(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function setTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* private mode: the choice just isn't remembered */
  }
  window.dispatchEvent(new CustomEvent('lector-theme', { detail: theme }))
}
