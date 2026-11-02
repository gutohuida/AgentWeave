import * as React from 'react'
import { TAB_LABELS } from '@/lib/navigation'

/** The traces view's mock controls. Where the view lives is the document's open question 1
 *  (a-traces-view-with-filters-grouping-and-stats), so the mock shows both:
 *  - `tab`: a Traces tab of its own in the top bar, after Activity;
 *  - `activity`: a fourth view inside Activity, beside Ledger, Activity and Logs.
 *  `#traces?place=activity` presets it. */
export type TracesPlacement = 'tab' | 'activity'

export const PLACEMENTS: Array<{ value: TracesPlacement; label: string }> = [
  { value: 'tab', label: 'Traces: own tab' },
  { value: 'activity', label: 'Traces: inside Activity' },
]

// The top bar names a tab through TAB_LABELS; the app has no Traces tab yet, so the mock adds the
// label for the `tab` placement. Nothing in src changes until the placement is decided.
;(TAB_LABELS as Record<string, string>).traces = 'Traces'

function initial(): TracesPlacement {
  const query = window.location.hash.split('?')[1] ?? ''
  return new URLSearchParams(query).get('place') === 'activity' ? 'activity' : 'tab'
}

let placement: TracesPlacement = initial()
const listeners = new Set<() => void>()

export function setTracesPlacement(next: TracesPlacement) {
  placement = next
  listeners.forEach((l) => l())
}

export function useTracesPlacement(): TracesPlacement {
  return React.useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => placement,
  )
}
