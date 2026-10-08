import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * The confirm before a delete the Hub cannot undo (F532: a document or a task). Shaped after
 * `ArchiveConfirmDialog` — focus starts on Cancel, Enter there cancels, the panel takes focus while
 * the delete is in flight — and it shows the Hub's refusal in place, so a delete the corpus or a
 * live run blocks says why without the operator losing their place.
 */
export function DeleteConfirmDialog({
  heading,
  body,
  confirmLabel,
  isPending,
  error = null,
  onCancel,
  onConfirm,
}: {
  heading: string
  /** What goes with it. Named, because "this cannot be undone" alone does not say what is lost. */
  body: string
  confirmLabel: string
  isPending: boolean
  error?: string | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

  useEffect(() => {
    if (isPending) panelRef.current?.focus()
  }, [isPending])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-confirm-title"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="lifted-surface w-[min(440px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="delete-confirm-title" className="text-sm font-semibold">
          {heading}
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {body} This cannot be undone.
        </p>

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
            data-testid="delete-confirm"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? 'Deleting…' : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}
