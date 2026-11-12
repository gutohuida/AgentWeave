import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import { useSetCapabilities, useSpecDocuments, type SpecDocumentRecord } from '@/api/spec'

/**
 * The capabilities a change names (`a-change-names-the-capabilities-it-changes`): the ones it
 * changes, the ones it will create by title, and where it was folded. The operator edits the link
 * until the change is folded; after a fold it is fixed, so the edit is not offered.
 */
export function ChangeCapabilities({ record }: { record: SpecDocumentRecord }) {
  const { data: documents, isError: documentsError, error: documentsReadError } = useSpecDocuments()
  const save = useSetCapabilities()
  const [editing, setEditing] = useState(false)
  const [changes, setChanges] = useState<string[]>([])
  const [creates, setCreates] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const link = record.capabilities ?? { changes: [], creates: [] }
  const all = documents?.documents ?? []
  const titleOf = (path: string) => all.find((d) => d.path === path)?.title ?? path
  const capabilities = all.filter((d) => d.kind === 'capability' && d.phase === 'current')
  const fixed = !!record.folded_into || record.phase === 'archived'

  function open() {
    setChanges(link.changes)
    setCreates(link.creates.map((c) => c.title).join('\n'))
    setReason('')
    setError(null)
    setEditing(true)
  }

  async function onSave() {
    setError(null)
    try {
      await save.mutateAsync({
        path: record.path,
        changes,
        creates: creates
          .split('\n')
          .map((title) => title.trim())
          .filter(Boolean)
          .map((title) => ({ title })),
        reason,
      })
      setEditing(false)
    } catch (refusal) {
      setError(readableApiError(refusal, 'The Hub did not accept those capabilities.'))
    }
  }

  const none = link.changes.length === 0 && link.creates.length === 0
  return (
    <div className="flex flex-col gap-1 text-xs" style={{ color: 'var(--text-3)' }}>
      <div className="flex flex-wrap items-center gap-2">
        <span>Capabilities</span>
        <span data-testid="change-capabilities" data-folded-into={record.folded_into ?? undefined}>
          {none ? 'none named' : null}
          {link.changes.map((path) => (
            <span key={path} data-path={path} className="mr-2">
              {titleOf(path)}
            </span>
          ))}
          {link.creates.map((c) => (
            <span key={c.title} data-new="true" className="mr-2">
              {c.title} (new)
            </span>
          ))}
          {record.folded_into ? <span> — folded into {titleOf(record.folded_into)}</span> : null}
        </span>
        {!fixed && !editing ? (
          <Button variant="ghost" size="xs" data-testid="change-capabilities-edit" onClick={open}>
            Edit
          </Button>
        ) : null}
      </div>
      {documentsError ? (
        <p role="alert" style={{ color: 'var(--amber)' }}>
          {readableApiError(documentsReadError, 'Could not load the capability documents.')}
        </p>
      ) : null}
      {editing ? (
        <div className="flex flex-col gap-1.5" data-testid="change-capabilities-form">
          <ul className="flex flex-col gap-0.5">
            {capabilities.map((c) => (
              <li key={c.path}>
                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    data-testid={`change-capabilities-pick-${c.path}`}
                    checked={changes.includes(c.path)}
                    onChange={(event) =>
                      setChanges((now) => (event.target.checked ? [...now, c.path] : now.filter((p) => p !== c.path)))
                    }
                  />
                  {c.title}
                </label>
              </li>
            ))}
          </ul>
          <textarea
            data-testid="change-capabilities-creates"
            aria-label="New capabilities to create, one title per line"
            placeholder="New capabilities, one title per line"
            rows={2}
            value={creates}
            onChange={(event) => setCreates(event.target.value)}
            style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
          <input
            type="text"
            data-testid="change-capabilities-reason"
            aria-label="Why the capabilities change"
            placeholder="Why (recorded)"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
          />
          {error ? (
            <p role="alert" data-testid="change-capabilities-error" style={{ color: 'var(--amber)' }}>
              {error}
            </p>
          ) : null}
          <div className="flex gap-2">
            <Button variant="primary" size="xs" data-testid="change-capabilities-save" disabled={save.isPending} onClick={onSave}>
              Save
            </Button>
            <Button variant="ghost" size="xs" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
