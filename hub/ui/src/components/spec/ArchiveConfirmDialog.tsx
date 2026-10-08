import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * Archive is the one control on `SpecPhaseBar` with no path back —
 * `spec_lifecycle.TRANSITIONS` has no edge out of `archived` — while Approve and
 * Reopen, its neighbours, are both reversible. That asymmetry is why this exists
 * and they fire on a single click. Lighter than `DeleteProjectDialog`'s
 * type-to-confirm: archiving one document is not deleting a project's entire
 * history, so naming the document and a Confirm click is enough.
 */
export function ArchiveConfirmDialog({
  title,
  isPending,
  error = null,
  reasonPrompt = null,
  onCancel,
  onConfirm,
}: {
  title: string
  isPending: boolean
  /** Set for an approved change folded into no capability: the archive then needs a reason saying
   *  why it changes none (`a-finished-change-is-folded-into-its-capability`), and Archive waits
   *  for one. */
  reasonPrompt?: string | null
  /** The Hub's refusal, shown in the dialog that asked for the archive (F205: archiving an
   *  exploring or proposed document is refused once it has produced work). */
  error?: string | null
  onCancel: () => void
  onConfirm: (reason: string) => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [reason, setReason] = useState('')
  const reasonMissing = reasonPrompt !== null && reason.trim() === ''
  useDialogFocus(true, panelRef, onCancel)

  // D6: Cancel and Archive both disable while pending, so the Archive button the operator just
  // pressed drops the keyboard to `<body>` behind the scrim. D1 cannot help — it runs once, on
  // open. Move focus to the panel itself (`tabIndex={-1}` from task 2.2) instead.
  useEffect(() => {
    if (isPending) panelRef.current?.focus()
  }, [isPending])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="archive-document-title"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="lifted-surface w-[min(420px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="archive-document-title" className="text-sm font-semibold">
          Archive “{title}”?
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          This cannot be undone. Once archived, there is no control in AgentWeave that reopens it.
        </p>

        {reasonPrompt !== null && (
          <label className="mt-3 flex flex-col gap-1 text-xs" style={{ color: 'var(--text-2)' }}>
            <span>{reasonPrompt}</span>
            <input
              type="text"
              data-testid="archive-reason"
              value={reason}
              maxLength={2000}
              onChange={(event) => setReason(event.target.value)}
              className="rounded-[var(--radius-sm)] px-1.5 py-1"
              style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
            />
          </label>
        )}

        {error && (
          <p role="alert" className="mt-3 text-xs" style={{ color: 'var(--amber)' }}>
            {error}
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isPending} data-dialog-initial-focus>
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            data-testid="archive-confirm"
            onClick={() => onConfirm(reason.trim())}
            disabled={isPending || reasonMissing}
          >
            {isPending ? 'Archiving…' : 'Archive'}
          </Button>
        </div>
      </div>
    </div>
  )
}
