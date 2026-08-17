import { useRef } from 'react'
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
  onCancel,
  onConfirm,
}: {
  title: string
  isPending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

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
        className="lifted-surface w-[min(420px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="archive-document-title" className="text-sm font-semibold">
          Archive “{title}”?
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          This cannot be undone. Once archived, there is no control in AgentWeave that reopens it.
        </p>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button variant="destructive" size="sm" onClick={onConfirm} disabled={isPending}>
            {isPending ? 'Archiving…' : 'Archive'}
          </Button>
        </div>
      </div>
    </div>
  )
}
