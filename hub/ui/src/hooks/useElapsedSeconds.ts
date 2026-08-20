import { useEffect, useState } from 'react'
import { hubDate } from '@/lib/hubTime'

/**
 * Seconds a run has been active; `null` while inactive.
 *
 * Prefers `since` — a timestamp the Hub recorded for the run — and falls back to the
 * moment `active` became true only when no such timestamp is available.
 *
 * That preference is the whole point. This used to time from the transition alone, which
 * meant the counter measured *how long this pane had been watching* rather than how long
 * the agent had been working. Leaving a conversation and coming back unmounts the pane, so
 * the operator returned to a run that had been going for minutes and found it reading a few
 * seconds (operator, 2026-08-20: "it goes back to 0 so we never know how long the agent has
 * been working"). Deriving from a server timestamp makes the value a property of the run
 * rather than of the component, so it survives navigation, remounts and a page reload.
 *
 * The fallback still matters: a run observed starting before its first entry has been
 * persisted has nothing to derive from, and a counter from the transition beats no counter.
 */
export function useElapsedSeconds(active: boolean, since?: string | null): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null)

  // Resolved outside the effect so a `since` that arrives late — the first entry landing a
  // moment after the run is observed — re-runs the effect and re-bases the count.
  const startedAt = resolveStart(since)

  useEffect(() => {
    if (!active) {
      setElapsed(null)
      return
    }
    const start = startedAt ?? Date.now()
    // Never render a negative age: a Hub clock marginally ahead of the browser's would
    // otherwise show "-1s" for the first second of every run.
    const read = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)))
    read()
    const id = setInterval(read, 1000)
    return () => clearInterval(id)
  }, [active, startedAt])

  return elapsed
}

/** Epoch milliseconds for a Hub timestamp, or null when absent or unparseable. */
function resolveStart(since?: string | null): number | null {
  if (!since) return null
  const parsed = hubDate(since).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

/** "12s" under a minute, "1:03" at or beyond it. */
export function formatElapsedSeconds(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${remainder.toString().padStart(2, '0')}`
}
