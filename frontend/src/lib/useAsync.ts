import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
  setData: (data: T) => void
}

/** Runs an async loader on mount (and when deps change) with loading/error state. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    loader()
      .then((result) => {
        if (alive) setData(result)
      })
      .catch((err: unknown) => {
        if (!alive) return
        setError(err instanceof ApiError ? err.detail : 'Something went wrong')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps])

  return { data, loading, error, reload, setData }
}
