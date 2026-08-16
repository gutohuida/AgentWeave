import { useState } from 'react'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { tint } from '@/lib/colorTint'
import {
  Charter,
  CharterCreate,
  useCharters,
  useCreateCharter,
  useDeleteCharter,
  useUpdateCharter,
} from '@/api/charters'
import { charterSummary } from '@/components/charters/charterSummary'

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
  // Which charters are open for reading. Held per-id rather than as a single selection so
  // two can be compared side by side — the whole reason this is a disclosure and not a
  // modal. Deliberately not persisted: it describes what is being looked at right now.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())

  const toggleExpanded = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  const collapse = (id: string) => {
    setExpanded((current) => {
      if (!current.has(id)) return current
      const next = new Set(current)
      next.delete(id)
      return next
    })
  }

  if (isLoading) {
    return (
      <SettingsSection title="Charters" description="Authored behavior and boundaries that can be assigned to an agent.">
        <div className="flex items-center gap-3 py-6">
          <Icon name="sync" size={24} className="animate-spin" style={{ color: 'var(--text-3)' }} />
          <span className="text-sm" style={{ color: 'var(--text-3)' }}>Loading charters...</span>
        </div>
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title="Charters"
      description="Authored behavior and boundaries that can be assigned to an agent."
      actions={(
        <Button variant="primary" size="sm" onClick={() => setCreating(true)}>
          <Icon name="add" size={18} />
          New Charter
        </Button>
      )}
    >
      {deleteError && (
        <div
          role="alert"
          className="mb-3 rounded-md px-3 py-2 text-xs"
          style={{ background: tint('var(--red)'), color: 'var(--red)' }}
        >
          {deleteError}
        </div>
      )}

      <div className="py-4">
        {charters.length === 0 ? (
          <EmptyState
            icon="assignment_ind"
            title="No charters yet"
            description="Create authored guidance, then bind it from an agent's detail view."
          />
        ) : (
          <div className="flex flex-col">
            {charters.map((charter) => {
              const isExpanded = expanded.has(charter.id)
              return (
                <div
                  key={charter.id}
                  className="border-b py-2.5"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <div className="flex items-start justify-between gap-4">
                    {/* The toggle target is the text region only. The destructive control
                        deliberately sits outside it — a click meant for the row must not be
                        able to land on delete. */}
                    <button
                      type="button"
                      onClick={() => toggleExpanded(charter.id)}
                      aria-expanded={isExpanded}
                      aria-controls={`charter-content-${charter.id}`}
                      aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${charter.name}`}
                      className="flex min-w-0 flex-1 items-start gap-1.5 text-left"
                    >
                      <Icon
                        name={isExpanded ? 'expand_more' : 'chevron_right'}
                        size={16}
                        className="mt-0.5 shrink-0"
                        style={{ color: 'var(--text-3)' }}
                      />
                      <span className="min-w-0">
                        <span className="block text-sm font-medium" style={{ color: 'var(--text)' }}>
                          {charter.name}
                        </span>
                        {!isExpanded && (
                          <span
                            className="mt-1 line-clamp-2 block text-xs"
                            style={{ color: 'var(--text-3)' }}
                          >
                            {charterSummary(charter.content) || 'No content'}
                          </span>
                        )}
                      </span>
                    </button>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button variant="ghost" size="icon-xs" onClick={() => setEditing(charter)} aria-label={`Edit ${charter.name}`}>
                        <Icon name="edit" size={16} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => {
                          setDeleteError(null)
                          deleteCharter.mutate(charter.id, {
                            onError: (error: unknown) => setDeleteError(errorDetail(error)),
                            onSuccess: () => collapse(charter.id),
                          })
                        }}
                        disabled={deleteCharter.isPending}
                        aria-label={`Delete ${charter.name}`}
                      >
                        <Icon name="delete" size={16} />
                      </Button>
                    </div>
                  </div>

                  {/* Styled as text, not as a form. A read-only textarea would reintroduce the
                      read/write ambiguity this view exists to remove. */}
                  {isExpanded && (
                    <div id={`charter-content-${charter.id}`} className="mt-2 pl-[22px]">
                      {charter.content ? (
                        <p
                          className="whitespace-pre-wrap font-mono text-xs leading-relaxed"
                          style={{ color: 'var(--text-2)' }}
                        >
                          {charter.content}
                        </p>
                      ) : (
                        <p className="text-xs italic" style={{ color: 'var(--text-3)' }}>
                          This charter has no content, so it contributes nothing to an agent&apos;s turn.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
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
    </SettingsSection>
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
      style={{ background: 'var(--scrim)' }}
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
          <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onSubmit({ name: name.trim(), content })}
            disabled={isPending || !name.trim()}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
