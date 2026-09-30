import { useSyncExternalStore } from 'react'

// Four screens, so a hash router is enough: #/  #/new  #/doc/<id>  #/doc/<id>/edit
export type Route = { name: 'home' } | { name: 'new' } | { name: 'doc'; id: string } | { name: 'edit'; id: string }

function parse(hash: string): Route {
  const path = hash.replace(/^#/, '')
  const edit = path.match(/^\/doc\/([\w-]+)\/edit/)
  if (edit?.[1]) return { name: 'edit', id: edit[1] }
  const doc = path.match(/^\/doc\/([\w-]+)/)
  if (doc?.[1]) return { name: 'doc', id: doc[1] }
  if (path.startsWith('/new')) return { name: 'new' }
  return { name: 'home' }
}

let cached = parse(location.hash)
function subscribe(cb: () => void): () => void {
  const handler = () => {
    cached = parse(location.hash)
    cb()
  }
  window.addEventListener('hashchange', handler)
  return () => window.removeEventListener('hashchange', handler)
}

export function currentRoute(): Route {
  return cached
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, () => cached)
}

function toHash(route: Route): string {
  switch (route.name) {
    case 'doc':
      return `/doc/${route.id}`
    case 'edit':
      return `/doc/${route.id}/edit`
    case 'new':
      return '/new'
    default:
      return '/'
  }
}

// A screen with unsaved work (the editor) can hold navigation until the user decides.
type Guard = (target: Route) => boolean
let guard: Guard | null = null

export function setNavigationGuard(g: Guard | null): void {
  guard = g
}

export function navigate(route: Route, { force = false }: { force?: boolean } = {}): void {
  if (!force && guard && !guard(route)) return
  location.hash = toHash(route)
}
