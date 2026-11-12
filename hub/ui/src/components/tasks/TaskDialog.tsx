import * as React from 'react'
import { TaskSheet } from './TaskSheet'
import '@/styles/task-sheet.css'

/** The opened task as the board opens it today: a centred dialog over the board, which dims and
 *  blurs behind it (`task-card-and-story-redesign`; the operator's call of 2026-08-17 that a ticket
 *  floats in the middle rather than taking the screen or a side). Closes on a click outside or
 *  Escape, as every dialog here does. The content is `TaskSheet` in its two-column layout. */
export function TaskDialog(props: Omit<React.ComponentProps<typeof TaskSheet>, 'layout'>) {
  const panelRef = React.useRef<HTMLDivElement>(null)
  const { onClose } = props
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div
      className="aw-task-scrim"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={props.task.title} className="aw-task-dialog">
        <TaskSheet {...props} layout="dialog" />
      </div>
    </div>
  )
}
