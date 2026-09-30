/** The reference data every page needs, fetched once. */

import type { ReactNode } from 'react'

import { api } from './api'
import { MetaContext } from './meta-context'
import { useAsync } from './useAsync'

export function MetaProvider({
  children,
}: {
  children: (state: { ready: boolean; error?: string }) => ReactNode
}) {
  const { data, error, reload } = useAsync(() => api.meta(), [])
  return (
    <MetaContext.Provider value={{ meta: data, reload }}>
      {/* `ready`, not `loading`. A later reload - after a dictionary edit, or after a
          sentence is saved to the memory - must not swap the page for a skeleton: that
          unmounts it and throws away the text the user was working on. */}
      {children({ ready: data !== undefined, error })}
    </MetaContext.Provider>
  )
}
