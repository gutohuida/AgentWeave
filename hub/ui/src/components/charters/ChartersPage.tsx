import { useState } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import {
  Charter,
  CharterCreate,
  useCharters,
  useCreateCharter,
  useDeleteCharter,
  useUpdateCharter,
} from '@/api/charters'

function errorDetail(error: unknown): string {
  if (!(error instanceof Error)) return 'Could not delete charter'
  try {
    const parsed = JSON.parse(error.message) as { detail?: string }
    return parsed.detail ?? error.message
  } catch {
    return error.message
  }
}

export function ChartersPage() {
  const { data: charters = [], isLoading } = useCharters()
  const createCharter = useCreateCharter()
  const updateCharter = useUpdateCharter()
  const deleteCharter = useDeleteCharter()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Charter | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center gap-3">
        <Icon name="sync" size={24} className="animate-spin" style={{ color: 'var(--text-3)' }} />
        <span className="text-sm" style={{ color: 'var(--text-3)' }}>Loading charters...</span>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-center justify-between p-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h1 className="text-lg font-normal" style={{ color: 'var(--text)' }}>Charters</h1>
          <p className="mt-0.5 text-xs" style={{ color: 'var(--text-3)' }}>
            Authored behavior and boundaries that can be assigned to an agent.
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex h-10 items-center gap-2 rounded-md px-4 text-[13px] font-medium"
          style={{ background: 'var(--blue)', color: '#fff' }}
        >
          <Icon name="add" size={18} />
          New Charter
        </button>
      </div>

      {deleteError && (
        <div
          role="alert"
          className="mx-4 mt-3 rounded-md px-3 py-2 text-xs"
          style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--red, #ef4444)' }}
        >
          {deleteError}
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
        {charters.length === 0 ? (
          <EmptyState
            icon="assignment_ind"
            title="No charters yet"
            description="Create authored guidance, then bind it from an agent's detail view."
          />
        ) : (
          <div className="grid max-w-3xl gap-2">
            {charters.map((charter) => (
              <div
                key={charter.id}
                className="flex items-start justify-between gap-4 rounded-md p-3"
                style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                    {charter.name}
                  </p>
                  <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-xs" style={{ color: 'var(--text-3)' }}>
                    {charter.content || 'No content'}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    onClick={() => setEditing(charter)}
                    className="rounded-md p-2"
                    style={{ color: 'var(--text-3)' }}
                    aria-label={`Edit ${charter.name}`}
                  >
                    <Icon name="edit" size={16} />
                  </button>
                  <button
                    onClick={() => {
                      setDeleteError(null)
                      deleteCharter.mutate(charter.id, {
                        onError: (error: unknown) => setDeleteError(errorDetail(error)),
                      })
                    }}
                    disabled={deleteCharter.isPending}
                    className="rounded-md p-2"
                    style={{ color: 'var(--text-3)' }}
                    aria-label={`Delete ${charter.name}`}
                  >
                    <Icon name="delete" size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {creating && (
        <CharterForm
          title="New Charter"
          initial={null}
          isPending={createCharter.isPending}
          onCancel={() => setCreating(false)}
          onSubmit={(values) => createCharter.mutate(values, { onSuccess: () => setCreating(false) })}
        />
      )}
      {editing && (
        <CharterForm
          title="Edit Charter"
          initial={editing}
          isPending={updateCharter.isPending}
          onCancel={() => setEditing(null)}
          onSubmit={(updates) => updateCharter.mutate(
            { id: editing.id, updates },
            { onSuccess: () => setEditing(null) },
          )}
        />
      )}
    </div>
  )
}

function CharterForm({
  title,
  initial,
  isPending,
  onCancel,
  onSubmit,
}: {
  title: string
  initial: Charter | null
  isPending: boolean
  onCancel: () => void
  onSubmit: (values: CharterCreate) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [content, setContent] = useState(initial?.content ?? '')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.5)' }}
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-label={title}
        className="w-full max-w-2xl rounded-lg p-5"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="mb-4 text-base font-medium" style={{ color: 'var(--text)' }}>{title}</h2>
        <label className="mb-1 block text-xs" style={{ color: 'var(--text-3)' }} htmlFor="charter-name">
          Name
        </label>
        <input
          id="charter-name"
          aria-label="Charter name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mb-3 w-full rounded-md px-3 py-2 text-sm"
          style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
        />
        <label className="mb-1 block text-xs" style={{ color: 'var(--text-3)' }} htmlFor="charter-content">
          Content
        </label>
        <textarea
          id="charter-content"
          aria-label="Charter content"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          className="h-72 w-full resize-y rounded-md px-3 py-2 font-mono text-sm"
          style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
        />
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-md px-4 py-2 text-sm" style={{ background: 'var(--surface-3)', color: 'var(--text-3)' }}>
            Cancel
          </button>
          <button
            onClick={() => onSubmit({ name: name.trim(), content })}
            disabled={isPending || !name.trim()}
            className="rounded-md px-4 py-2 text-sm font-medium"
            style={{ background: 'var(--blue)', color: '#fff', opacity: isPending || !name.trim() ? 0.6 : 1 }}
          >
            {isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
