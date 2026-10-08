import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * Retiring a capability that no longer describes the product (F536). Like archiving, it has no way
 * back: the capability's requirements are retired and nothing can be merged into it again. A reason
 * is required; the capability that absorbed it is optional and chosen from the current ones.
 */
export function RetireCapabilityDialog({
  title,
  capabilities,
  isPending,
  error = null,
  onCancel,
  onConfirm,
}: {
  title: string
  /** The other current capabilities, any of which may have absorbed this one. */
  capabilities: { path: string; title: string }[]
  isPending: boolean
  /** The Hub's refusal (open work on its requirements, a bad absorber), shown where it was asked. */
  error?: string | null
  onCancel: () => void
  onConfirm: (reason: string, absorbedBy: string | null) => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [reason, setReason] = useState('')
  const [absorbedBy, setAbsorbedBy] = useState('')
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
      aria-labelledby="retire-capability-title"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="lifted-surface w-[min(460px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="retire-capability-title" className="text-sm font-semibold">
          Retire “{title}”?
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          Its requirements are retired and leave coverage, and nothing can be merged into it again.
          The file stays as the record of what it said. This cannot be undone.
        </p>

        <label className="mt-3 flex flex-col gap-1 text-xs" style={{ color: 'var(--text-2)' }}>
          <span>Why does it no longer describe the product?</span>
          <textarea
            data-testid="retire-reason"
            value={reason}
            maxLength={2000}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
            className="rounded-[var(--radius-sm)] px-1.5 py-1"
            style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
        </label>

        <label className="mt-3 flex flex-col gap-1 text-xs" style={{ color: 'var(--text-2)' }}>
          <span>Absorbed by (optional)</span>
          <select
            data-testid="retire-absorbed-by"
            value={absorbedBy}
            onChange={(event) => setAbsorbedBy(event.target.value)}
            className="rounded-[var(--radius-sm)] px-1.5 py-1"
            style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
          >
            <option value="">No capability</option>
            {capabilities.map((capability) => (
              <option key={capability.path} value={capability.path}>
                {capability.title}
              </option>
            ))}
          </select>
        </label>

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
            data-testid="retire-confirm"
            onClick={() => onConfirm(reason.trim(), absorbedBy || null)}
            disabled={isPending || reason.trim() === ''}
          >
            {isPending ? 'Retiring…' : 'Retire'}
          </Button>
        </div>
      </div>
    </div>
  )
}
