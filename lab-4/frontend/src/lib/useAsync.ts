/**
 * The one data-fetching hook this application needs.
 *
 * Every screen here loads once and reloads on an explicit action, so a caching library
 * would carry no weight. What the hook does guarantee is the three states a screen must
 * always handle - loading, error, loaded - and that a response arriving after the
 * component unmounted is discarded rather than setting state on a dead component.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface AsyncState<T> {
  data: T | undefined
  error: string | undefined
  loading: boolean
  reload: () => void
  setData: (value: T) => void
}

export function useAsync<T>(load: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<string | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    let current = true
    setLoading(true)
    setError(undefined)
    load()
      .then((value) => {
        if (current && alive.current) setData(value)
      })
      .catch((cause: unknown) => {
        if (current && alive.current) {
          setError(cause instanceof Error ? cause.message : 'Something went wrong')
        }
      })
      .finally(() => {
        if (current && alive.current) setLoading(false)
      })
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  return { data, error, loading, reload, setData }
}

/** For actions: tracks the in-flight state and the last error of a one-shot call. */
export function useAction(): {
  run: <T>(task: () => Promise<T>) => Promise<T | undefined>
  busy: boolean
  error: string | undefined
  clearError: () => void
} {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | undefined>(undefined)

  const run = useCallback(async <T,>(task: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true)
    setError(undefined)
    try {
      return await task()
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : 'Something went wrong')
      return undefined
    } finally {
      setBusy(false)
    }
  }, [])

  return { run, busy, error, clearError: () => setError(undefined) }
}
