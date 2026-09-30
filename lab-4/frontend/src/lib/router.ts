/**
 * A hash router in thirty lines.
 *
 * The application has four pages and no nested routes; a routing library would be more
 * configuration than code. A hash route also means the static nginx build needs no
 * rewrite rules and deep links survive a refresh.
 */

import { useEffect, useState } from 'react'

export const ROUTES = ['translate', 'dictionary', 'memory', 'help'] as const
export type Route = (typeof ROUTES)[number]

function parse(hash: string): Route {
  const name = hash.replace(/^#\/?/, '').split('?')[0]
  return (ROUTES as readonly string[]).includes(name) ? (name as Route) : 'translate'
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = (next: Route) => {
    window.location.hash = `#/${next}`
  }

  return [route, navigate]
}
