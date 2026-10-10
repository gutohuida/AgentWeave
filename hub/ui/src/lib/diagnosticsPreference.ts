// Whether the conversation draws its `diagnostic` cards: one browser-wide value, not one per
// conversation (a debugging switch should not have to be flipped in every thread). Same bounded
// pattern as composerDrafts.ts: anything unreadable means "shown", and a write failure is
// swallowed so the control still works for the session without persistence.
import { useSyncExternalStore } from 'react'

const STORAGE_KEY = 'aw.conversation.diagnostics.v1'
const CHANGED_EVENT = 'aw:conversation-diagnostics-changed'

export function readDiagnosticsHidden(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'hidden'
  } catch {
    return false
  }
}

export function writeDiagnosticsHidden(hidden: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, hidden ? 'hidden' : 'shown')
  } catch {
    // Persisting the choice is best-effort.
  }
  window.dispatchEvent(new Event(CHANGED_EVENT))
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED_EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(CHANGED_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

/** The header control and the timeline read the same value without a prop between them. */
export function useDiagnosticsHidden(): [boolean, (hidden: boolean) => void] {
  const hidden = useSyncExternalStore(subscribe, readDiagnosticsHidden, () => false)
  return [hidden, writeDiagnosticsHidden]
}
