import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * `DELETE /charters/{id}` is a hard delete: `Charter` has no archived flag, the route removes the
 * row, and nothing in AgentWeave keeps a copy (F186). The route refuses only while an agent is
 * bound to the charter; an unbound charter goes on the first request. So the one click that used
 * to fire the delete now opens this.
 *
 * Shaped after `ClearInstructionsDialog`: it names the charter and says how much text would be
 * lost, because a confirmation that only asks "are you sure?" transfers no information. Rows can
 * share a name (F183), so the count is also what tells two same-named rows apart.
 *
 * Confirm closes the dialog and fires the delete in one act, as there. A refusal (the 409 for a
 * bound charter) renders in the page's alert, which is where the delete's errors already went.
 */
export function DeleteCharterDialog({
  name,
  content,
  onCancel,
  onConfirm,
}: {
  name: string
  content: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

  const trimmed = content.replace(/\n+$/, '')
  const lines = trimmed ? trimmed.split('\n').length : 0
  const size = lines === 0
    ? 'It has no content'
    : `Its ${lines === 1 ? '1 line' : `${lines} lines`} of authored text will be lost`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="delete-charter-title"
      onClick={(event) => { if (event.target === event.currentTarget) onCancel() }}
    >
      <div
        ref={panelRef}
        className="lifted-surface w-[min(440px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="delete-charter-title" className="text-sm font-semibold">
          Delete the charter “{name}”?
        </h2>
        <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-3)' }}>
          {size}. <strong style={{ color: 'var(--text-2)' }}>AgentWeave keeps no copy</strong> —
          there is no archive and no undo, so the only way back is to write it again.
        </p>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" onClick={onConfirm}>
            Delete charter
          </Button>
        </div>
      </div>
    </div>
  )
}
