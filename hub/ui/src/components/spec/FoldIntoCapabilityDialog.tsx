import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { readableApiError } from '@/api/client'
import {
  useFoldDocument,
  useFoldDraft,
  useSpecDocuments,
  type SpecFoldDraftRequirement,
} from '@/api/spec'

interface Row {
  from: string
  key: string
  statement: string
  draftStatement: string
  include: boolean
}

function rowsFrom(requirements: SpecFoldDraftRequirement[]): Row[] {
  return requirements.map((r) => ({
    from: r.from,
    key: r.key,
    statement: r.statement,
    draftStatement: r.statement,
    include: true,
  }))
}

/**
 * The operator's close-out of a finished change (`a-finished-change-is-folded-into-its-capability`):
 * pick the capability, read the Hub's draft — the change's requirements copied in under
 * `<change-slug>-<key>` — edit a key or a statement where the change's wording does not suit the
 * capability, and confirm. One confirm folds through the merge and, by default, archives the change.
 * A change that touches two capabilities is folded twice, leaving archive off the first time.
 */
export function FoldIntoCapabilityDialog({
  path,
  title,
  onClose,
}: {
  path: string
  title: string
  onClose: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onClose)
  const { data: documents, isError: documentsError, error: documentsReadError } = useSpecDocuments()
  const capabilities = (documents?.documents ?? []).filter((d) => d.kind === 'capability')
  const [into, setInto] = useState<string | null>(null)
  const draft = useFoldDraft(path, into)
  const fold = useFoldDocument()
  const [rows, setRows] = useState<Row[]>([])
  const [archive, setArchive] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // A new draft for each capability chosen; edits made against another capability do not carry.
  useEffect(() => {
    setRows(draft.data ? rowsFrom(draft.data.requirements) : [])
  }, [draft.data])

  const collisions = new Set(draft.data?.collisions ?? [])
  const included = rows.filter((row) => row.include)
  const blocked =
    !into ||
    included.length === 0 ||
    included.some((row) => collisions.has(row.key) || row.key.trim() === '') ||
    fold.isPending

  function update(from: string, change: Partial<Row>) {
    setRows((current) => current.map((row) => (row.from === from ? { ...row, ...change } : row)))
  }

  async function onConfirm() {
    if (!into || blocked) return
    setError(null)
    try {
      await fold.mutateAsync({
        path,
        into,
        archive,
        requirements: included.map((row) => ({
          key: row.from,
          as_key: row.key.trim(),
          ...(row.statement !== row.draftStatement ? { statement: row.statement } : {}),
        })),
      })
      onClose()
    } catch (refusal) {
      setError(readableApiError(refusal, 'The Hub refused to fold this change.'))
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="fold-document-title"
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="lifted-surface flex max-h-[calc(100vh-64px)] w-[min(640px,calc(100vw-32px))] flex-col gap-3 overflow-y-auto p-5 text-xs"
        style={{ background: 'var(--surface)' }}
      >
        <h2 id="fold-document-title" className="text-sm font-semibold">
          Fold “{title}” into a capability
        </h2>
        <p style={{ color: 'var(--text-3)' }}>
          The change’s requirements are copied into the capability you choose. Edit a key or a
          statement where the change’s wording does not suit the capability.
        </p>

        <label className="flex items-center gap-2">
          <span style={{ color: 'var(--text-2)' }}>Capability</span>
          <select
            data-testid="fold-capability"
            value={into ?? ''}
            onChange={(event) => setInto(event.target.value || null)}
            className="min-w-0 flex-1 rounded-[var(--radius-sm)] px-1.5 py-1"
            style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          >
            <option value="">Choose…</option>
            {capabilities.map((capability) => (
              <option key={capability.path} value={capability.path}>
                {capability.title}
              </option>
            ))}
          </select>
        </label>

        {/* An empty picker after a failed read would read as "this project has no capabilities". */}
        {documentsError && (
          <p role="alert" style={{ color: 'var(--amber)' }}>
            {readableApiError(documentsReadError, 'Could not load the capability documents.')}
          </p>
        )}

        {draft.isError && (
          <p role="alert" style={{ color: 'var(--amber)' }}>
            {readableApiError(draft.error, 'The Hub could not draft this fold.')}
          </p>
        )}

        {rows.length > 0 && (
          <ul className="flex flex-col gap-2" data-testid="fold-rows">
            {rows.map((row) => {
              const colliding = row.include && collisions.has(row.key)
              return (
                <li
                  key={row.from}
                  className="flex flex-col gap-1 rounded-[var(--radius-sm)] p-2"
                  style={{ background: 'var(--surface-2)', opacity: row.include ? 1 : 0.6 }}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      data-testid={`fold-req-include-${row.from}`}
                      aria-label={`Fold ${row.from}`}
                      checked={row.include}
                      onChange={(event) => update(row.from, { include: event.target.checked })}
                    />
                    <span style={{ color: 'var(--text-3)' }}>{row.from} →</span>
                    <input
                      type="text"
                      data-testid={`fold-req-key-${row.from}`}
                      aria-label={`Capability key for ${row.from}`}
                      value={row.key}
                      maxLength={64}
                      disabled={!row.include}
                      onChange={(event) => update(row.from, { key: event.target.value })}
                      className="min-w-0 flex-1 rounded-[var(--radius-sm)] px-1.5 py-0.5 font-mono"
                      style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
                    />
                  </div>
                  <textarea
                    data-testid={`fold-req-statement-${row.from}`}
                    aria-label={`Statement for ${row.from}`}
                    value={row.statement}
                    rows={3}
                    disabled={!row.include}
                    onChange={(event) => update(row.from, { statement: event.target.value })}
                    className="rounded-[var(--radius-sm)] px-1.5 py-1"
                    style={{ background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)' }}
                  />
                  {colliding && (
                    <span
                      data-testid={`fold-req-collision-${row.from}`}
                      className="flex items-center gap-1.5"
                      style={{ color: 'var(--amber)' }}
                    >
                      <Icon name="warning" size={13} />
                      The capability already has {row.key}: rename it, or leave it out.
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        <label className="flex items-center gap-1.5" style={{ color: 'var(--text-2)' }}>
          <input
            type="checkbox"
            data-testid="fold-archive"
            checked={archive}
            onChange={(event) => setArchive(event.target.checked)}
          />
          Archive the change once it is folded (leave this off when it still goes into another
          capability)
        </label>

        {error && (
          <p role="alert" data-testid="fold-error" style={{ color: 'var(--amber)' }}>
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={fold.isPending} data-dialog-initial-focus>
            Cancel
          </Button>
          <Button variant="primary" size="sm" data-testid="fold-confirm" onClick={onConfirm} disabled={blocked}>
            {fold.isPending ? 'Folding…' : archive ? 'Fold and archive' : 'Fold'}
          </Button>
        </div>
      </div>
    </div>
  )
}
