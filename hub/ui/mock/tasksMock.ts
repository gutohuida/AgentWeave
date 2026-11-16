import * as React from 'react'

/** The Tasks screen's mock controls: which Dependencies view to show, and whether to add a wider
 *  build than the recorded ones (every recorded document is a straight chain). */
export interface TasksMockControls {
  deps: 'map' | 'list'
  wide: boolean
}

const query = new URLSearchParams(window.location.hash.split('?')[1] ?? '')
let controls: TasksMockControls = { deps: query.get('deps') === 'list' ? 'list' : 'map', wide: query.get('wide') !== 'off' }
const listeners = new Set<() => void>()

export function setTasksMockControls(next: Partial<TasksMockControls>) {
  controls = { ...controls, ...next }
  listeners.forEach((l) => l())
}

export function useTasksMockControls(): TasksMockControls {
  return React.useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => controls,
  )
}
