import { useState, useEffect, useCallback } from 'react'
import { flushSync } from 'react-dom'

export function useApi(fetcher, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetcher()
      setData(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, deps)

  // Silent refetch: updates data without toggling loading state.
  // Uses flushSync to commit the React state update synchronously, THEN restores
  // scroll — this prevents React's async commit from overriding the scroll restore.
  const silentRefetch = useCallback(async () => {
    const savedScrollY = window.scrollY
    try {
      const result = await fetcher()
      // flushSync forces React to commit setData synchronously before returning,
      // so window.scrollTo runs AFTER the DOM is updated (not before).
      flushSync(() => {
        setData(result)
      })
      if (savedScrollY > 0) {
        window.scrollTo({ top: savedScrollY, behavior: 'instant' })
      }
    } catch {
      // swallow errors silently — don't disturb the UI
    }
  }, deps)

  useEffect(() => {
    refetch()
  }, [refetch])

  return { data, loading, error, refetch, silentRefetch }
}
