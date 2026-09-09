import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * Saving an empty editor over stored instructions destroys them, and nothing in AgentWeave keeps a
 * copy — the row is upserted in place, there is no history table and no undo control anywhere on
 * the page. So that one class of Save asks first.
 *
 * Shaped after `ArchiveConfirmDialog` rather than `DeleteProjectDialog`: the latter's
 * type-to-confirm exists, by its own docstring, because no other destructive control removes as
 * much at once, and one project's instructions are not that. Naming the project and a Confirm
 * click is enough.
 *
 * **It says how much would be lost.** A confirmation that only asks "are you sure?" transfers no
 * information and earns its dismissal (`design.md` D3), so the line count of the text that was
 * actually read is stated, and so is the fact the operator cannot discover anywhere else: no copy
 * is kept.
 *
 * **No `isPending`, unlike `ArchiveConfirmDialog`.** Confirm closes the dialog and fires the write
 * in one act, so there is no interval in which a second Confirm click is reachable and nothing to
 * disable. Keeping it open would also hide the save acknowledgement, which renders in
 * `SettingsSection`'s heading behind the scrim.
 */
export function ClearInstructionsDialog({
  projectName,
  storedContent,
  onCancel,
  onConfirm,
}: {
  projectName: string
  storedContent: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

  // Trailing newlines are stripped before counting: a file that ends in a newline is not one line
  // longer than the same file without it, and the count is being read by someone deciding whether
  // this is the three-word note or the four hundred lines of project rules.
  const lines = storedContent.replace(/\n+$/, '').split('\n').length

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="clear-instructions-title"
      // A click on the scrim is Cancel, like Escape. Guarded on the target so a click that starts
      // inside the panel and drifts out — a select-drag over the heading — does not dismiss it.
      onClick={(event) => { if (event.target === event.currentTarget) onCancel() }}
    >
      <div
        ref={panelRef}
        className="lifted-surface w-[min(440px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="clear-instructions-title" className="text-sm font-semibold">
          Clear the instructions for “{projectName}”?
        </h2>
        <p className="mt-1 text-xs leading-relaxed" style={{ color: 'var(--text-3)' }}>
          Saving now replaces {lines === 1 ? '1 line' : `${lines} lines`} of stored instructions with
          nothing. <strong style={{ color: 'var(--text-2)' }}>AgentWeave keeps no copy</strong> —
          there is no history and no undo, so the only way back is to write them again.
        </p>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" onClick={onConfirm}>
            Clear instructions
          </Button>
        </div>
      </div>
    </div>
  )
}
