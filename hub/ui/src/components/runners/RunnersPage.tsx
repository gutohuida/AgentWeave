import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { SettingsSection } from '@/components/environment/SettingsSection'
import {
  useRunners,
  useCreateRunner,
  useUpdateRunner,
  useDeleteRunner,
  Runner,
  RunnerCli,
} from '@/api/runners'

const CLI_OPTIONS: RunnerCli[] = ['claude', 'codex']

function extractErrorDetail(err: unknown): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: string }
      if (parsed.detail) return parsed.detail
    } catch {
      // not JSON — fall through to the raw message
    }
    return err.message
  }
  return 'Could not delete runner'
}

export function RunnersPage() {
  const { data: runners, isLoading } = useRunners()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Runner | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const createRunner = useCreateRunner()
  const updateRunner = useUpdateRunner()
  const deleteRunner = useDeleteRunner()

  const handleDelete = (id: string) => {
    setDeleteError(null)
    deleteRunner.mutate(id, {
      onError: (err: unknown) => {
        setDeleteError(extractErrorDetail(err))
      },
    })
  }

  if (isLoading) {
    return (
      <SettingsSection title="Runners" description="Reusable execution capability — which CLI and model an agent launches with.">
        <div className="flex items-center gap-3 py-6">
          <Icon name="sync" size={24} className="animate-spin" style={{ color: 'var(--text-3)' }} />
          <span className="text-sm" style={{ color: 'var(--text-3)' }}>Loading runners…</span>
        </div>
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title="Runners"
      description="Reusable execution capability — which CLI and model an agent launches with."
      actions={(
        <Button variant="primary" size="sm" onClick={() => setShowForm(true)}>
          <Icon name="add" size={18} />
          New Runner
        </Button>
      )}
    >
      {deleteError && (
        <div
          role="alert"
          className="mb-3 px-3 py-2 rounded-md text-xs"
          style={{ background: 'rgba(239,68,68,0.1)', color: 'var(--red, #ef4444)' }}
        >
          {deleteError}
        </div>
      )}

      <div className="py-4">
        {!runners || runners.length === 0 ? (
          <EmptyState
            icon="dns"
            title="No runners yet"
            description="Runners are seeded automatically on first start (one per supported CLI). Create a custom one to vary model or name."
          />
        ) : (
          <div className="flex flex-col">
            {runners.map((runner) => (
              <div
                key={runner.id}
                className="flex items-center justify-between border-b py-2.5"
                style={{ borderColor: 'var(--border)' }}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                      {runner.name}
                    </span>
                    <span
                      className="text-[11px] font-medium px-2 py-0.5 rounded-full capitalize"
                      style={{ background: 'var(--surface-3)', color: 'var(--text-3)' }}
                    >
                      {runner.cli}
                    </span>
                  </div>
                  {runner.model && (
                    <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
                      {runner.model}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button variant="ghost" size="icon-xs" onClick={() => setEditing(runner)} title="Edit" aria-label={`Edit ${runner.name}`}>
                    <Icon name="edit" size={16} />
                  </Button>
                  <Button variant="ghost" size="icon-xs" onClick={() => handleDelete(runner.id)} disabled={deleteRunner.isPending} title="Delete" aria-label={`Delete ${runner.name}`}>
                    <Icon name="delete" size={16} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <RunnerForm
          title="New Runner"
          initial={null}
          isPending={createRunner.isPending}
          onCancel={() => setShowForm(false)}
          onSubmit={(values) =>
            createRunner.mutate(values, { onSuccess: () => setShowForm(false) })
          }
        />
      )}

      {editing && (
        <RunnerForm
          title="Edit Runner"
          initial={editing}
          isPending={updateRunner.isPending}
          onCancel={() => setEditing(null)}
          onSubmit={(values) =>
            updateRunner.mutate(
              { id: editing.id, updates: { name: values.name, model: values.model } },
              { onSuccess: () => setEditing(null) },
            )
          }
        />
      )}
    </SettingsSection>
  )
}

interface RunnerFormValues {
  name: string
  cli: RunnerCli
  model?: string
}

function RunnerForm({
  title,
  initial,
  isPending,
  onCancel,
  onSubmit,
}: {
  title: string
  initial: Runner | null
  isPending: boolean
  onCancel: () => void
  onSubmit: (values: RunnerFormValues) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [cli, setCli] = useState<RunnerCli>(initial?.cli ?? 'claude')
  const [model, setModel] = useState(initial?.model ?? '')

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{ background: 'rgba(0,0,0,0.5)' }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-lg p-5"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-medium mb-4" style={{ color: 'var(--text)' }}>
          {title}
        </h2>
        <div className="space-y-3">
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Name
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
              placeholder="e.g. Claude Opus"
            />
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              CLI
            </label>
            <select
              value={cli}
              disabled={!!initial}
              onChange={(e) => setCli(e.target.value as RunnerCli)}
              className="w-full px-3 py-2 rounded-md text-sm capitalize"
              style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
            >
              {CLI_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Model (optional)
            </label>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{ background: 'var(--surface-2)', color: 'var(--text)', border: '1px solid var(--border)' }}
              placeholder="e.g. claude-sonnet-5"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-5">
          <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onSubmit({ name, cli, model: model || undefined })}
            disabled={isPending || !name.trim()}
          >
            {isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
