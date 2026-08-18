import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchAllPages } from './client'

/**
 * Shared data-fetching hooks (H2). Before these, every page hand-rolled the
 * same `useState<T|null>` + `useEffect(load)` + `.catch(setError)` block, and
 * none of them guarded against a stale response landing after a newer one
 * (navigate away and back quickly, or a dependency change mid-flight).
 *
 * `useApiQuery` owns: loading/data/error state, a stale-response guard (only
 * the latest in-flight request may set state), the ApiError → message
 * mapping, and `reload()` for "refresh after a mutation".
 */
export interface QueryState<T> {
  data: T | null
  error: string | null
  /** true only for the first load (data === null); reloads keep the old data visible */
  loading: boolean
  reload: () => void
  setData: (updater: T | ((current: T | null) => T | null)) => void
}

export function useApiQuery<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
  options: { errorMessage?: string; enabled?: boolean } = {},
): QueryState<T> {
  const { errorMessage = 'Failed to load.', enabled = true } = options
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const latest = useRef(0)
  // The fetcher is re-created every render by callers (closures over props);
  // keep the newest one in a ref and let `deps` decide when to re-run.
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  useEffect(() => {
    if (!enabled) return
    const id = ++latest.current
    setError(null)
    fetcherRef
      .current()
      .then((result) => {
        if (id === latest.current) setData(result)
      })
      .catch((err: unknown) => {
        if (id !== latest.current) return
        setError(err instanceof ApiError && err.status !== 500 ? err.message : errorMessage)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const setDataStable = useCallback((updater: T | ((current: T | null) => T | null)) => {
    setData((current) => (typeof updater === 'function' ? (updater as (c: T | null) => T | null)(current) : updater))
  }, [])

  return { data, error, loading: data === null && error === null, reload, setData: setDataStable }
}

/** Sugar for the most common case: a whole cursor-paginated collection. */
export function useAllPages<T>(path: string | null, deps: readonly unknown[] = [], errorMessage?: string) {
  return useApiQuery<T[]>(() => fetchAllPages<T>(path as string), [path, ...deps], {
    errorMessage,
    enabled: path !== null,
  })
}

/**
 * Wraps a mutating call with the busy/error state every form and action
 * button was re-implementing. `run` resolves to the result or `undefined`
 * on failure (the error is exposed as state, not thrown, so callers don't
 * need their own try/catch).
 */
export function useMutation<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
  options: { onSuccess?: (result: TResult, ...args: TArgs) => void; errorMessage?: string } = {},
) {
  const { onSuccess, errorMessage = 'Request failed.' } = options
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const onSuccessRef = useRef(onSuccess)
  onSuccessRef.current = onSuccess

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | undefined> => {
      setError(null)
      setBusy(true)
      try {
        const result = await fnRef.current(...args)
        onSuccessRef.current?.(result, ...args)
        return result
      } catch (err) {
        setError(err instanceof ApiError ? err.message : errorMessage)
        return undefined
      } finally {
        setBusy(false)
      }
    },
    [errorMessage],
  )
  const reset = useCallback(() => setError(null), [])
  return { run, busy, error, reset }
}
