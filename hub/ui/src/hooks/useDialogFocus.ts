import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[href]',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/** The dialogs currently holding the keyboard, oldest first. Only the newest wraps Tab: with two
 *  open, the older one's listener would otherwise see focus "outside" its panel — inside the newer
 *  dialog — and pull it back behind that dialog (F307's fix makes that reachable). */
const openDialogs: object[] = []

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
    const token = {}
    openDialogs.push(token)
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
      if (openDialogs[openDialogs.length - 1] !== token) return
      const focusable = [...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      // F307: focus can still be outside the panel — on the control that opened it, which this hook
      // does not move focus away from. The branches below act only on `first` and `last`, so the
      // first Tab used to fall through to the browser's order and land behind the scrim. A Tab
      // from outside enters the panel instead. (Where focus starts when a dialog opens is a
      // separate question, D13's; this only keeps the cycle closed from the first press.)
      const active = document.activeElement
      if (!panelRef.current?.contains(active)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
        return
      }
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
      openDialogs.splice(openDialogs.indexOf(token), 1)
      returnFocusTo?.focus()
    }
  }, [active, panelRef])
}
