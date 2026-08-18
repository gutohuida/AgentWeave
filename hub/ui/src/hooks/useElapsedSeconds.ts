import { useEffect, useRef, useState } from 'react'

/**
 * Seconds elapsed since `active` most recently became true; `null` while inactive.
 * Timed from the transition itself, not from any server-reported start time — a run
 * already in progress when this mounts reads from when it was first observed, not
 * from when it truly began.
 */
export function useElapsedSeconds(active: boolean): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null)
  const startRef = useRef<number | null>(null)

  useEffect(() => {
    if (!active) {
      startRef.current = null
      setElapsed(null)
      return
    }
    const start = Date.now()
    startRef.current = start
    setElapsed(0)
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [active])

  return elapsed
}

/** "12s" under a minute, "1:03" at or beyond it. */
export function formatElapsedSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}
