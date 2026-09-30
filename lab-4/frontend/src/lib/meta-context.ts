/** The context itself and its hook, kept out of the provider module.
 *
 * React Fast Refresh only recognises a module as a component module when every export is a
 * component, so the value and the hook live here and `meta.tsx` exports only `MetaProvider`.
 */

import { createContext, useContext } from 'react'

import type { Meta } from './types'

export interface MetaValue {
  meta: Meta | undefined
  reload: () => void
}

export const MetaContext = createContext<MetaValue>({ meta: undefined, reload: () => {} })

export const useMeta = (): MetaValue => useContext(MetaContext)
