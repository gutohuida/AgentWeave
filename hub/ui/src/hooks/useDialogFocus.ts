import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function useDialogFocus(
  active: boolean,
  panelRef: RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    if (!active) return
    const returnFocusTo = document.activeElement as HTMLElement | null
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        // Something nearer the key has already answered it — a nested picker, a menu, an input
        // collecting an answer — and calling preventDefault() is how it says so. Stand down.
        //
        // Why this check is sufficient, and not merely present: this listener is on `document`
        // and in the bubble phase, so it is structurally the last handler in the propagation
        // path to see the key. Every React handler in the tree, and every capture-phase listener
        // anywhere, has already run by the time we are called. There is no handler that could
        // claim the key *after* us and be missed by this flag. That is also why the binding and
        // the phase are load-bearing (design.md D3): moving to capture would put this hook ahead
        // of the nested owners it is meant to defer to, and this condition would then read a flag
        // nobody had set yet.
        if (event.defaultPrevented) return
        event.preventDefault()
        closeRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = [...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      returnFocusTo?.focus()
    }
  }, [active, panelRef])
}
