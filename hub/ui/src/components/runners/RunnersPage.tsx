import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { EmptyState } from '@/components/common/EmptyState'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { SettingsSection } from '@/components/environment/SettingsSection'
import { tint } from '@/lib/colorTint'
import {
  useRunners,
  useCreateRunner,
  useUpdateRunner,
  useDeleteRunner,
  Runner,
  RunnerCli,
} from '@/api/runners'
import { useModelCatalog } from '@/api/modelCatalog'
import { readableApiError } from '@/api/client'

const CLI_OPTIONS: RunnerCli[] = ['claude', 'codex']

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
        setDeleteError(readableApiError(err, 'Could not delete runner'))
      },
    })
  }

  if (isLoading) {
    return (
      <SettingsSection title="Runners" description="Reusable execution capability — which CLI and model an agent launches with.">
        <div aria-label="Loading runners" className="space-y-2 py-4">
          {[0, 1, 2].map((row) => <div key={row} className="skeleton h-14 w-full" />)}
        </div>
      </SettingsSection>
    )
  }

  return (
    <SettingsSection
      title="Runners"
      description="Reusable execution capability — which CLI and model an agent launches with."
      actions={(
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            // The mutations live here and outlive the dialog, so a refusal from the last attempt
            // would still be on `createRunner.error` when this one opens.
            createRunner.reset()
            setShowForm(true)
          }}
        >
          <Icon name="add" size={18} />
          New Runner
        </Button>
      )}
    >
      {deleteError && (
        <div
          role="alert"
          className="mb-3 px-3 py-2 rounded-md text-xs"
          style={{ background: tint('var(--red)'), color: 'var(--red)' }}
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
                className="row-group interactive-card flex items-center justify-between rounded-md border-b px-2 py-2.5"
                style={{ borderColor: 'var(--border)' }}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>
                      {runner.name}
                    </span>
                    <span
                      className="aw-chip capitalize"
                      style={{ background: 'var(--surface-3)', color: 'var(--text-3)' }}
                    >
                      {runner.cli}
                    </span>
                  </div>
                  {runner.model && (
                    <p className="text-xs mt-1 flex items-center gap-1.5" style={{ color: 'var(--text-3)' }}>
                      <span>{runner.model}</span>
                      {runner.model_unrecognised && (
                        <span
                          className="aw-chip"
                          style={{ background: tint('var(--amber)'), color: 'var(--amber)' }}
                          title="The catalog does not declare this model for this CLI. The runner still works; editing it keeps the model unless you change it."
                        >
                          Unrecognised
                        </span>
                      )}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button variant="ghost" size="icon-xs" onClick={() => { updateRunner.reset(); setEditing(runner) }} title="Edit" aria-label={`Edit ${runner.name}`}>
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
          error={createRunner.error}
          onCancel={() => { createRunner.reset(); setShowForm(false) }}
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
          error={updateRunner.error}
          onCancel={() => { updateRunner.reset(); setEditing(null) }}
          onSubmit={(values) =>
            updateRunner.mutate(
              // `model` is always sent on edit, and `null` is how the operator's "Provider default"
              // choice reaches the Hub — `undefined` would be dropped by JSON.stringify and read as
              // "leave it alone" (RunnerUpdate, and update_runner's `model_fields_set` gate).
              { id: editing.id, updates: { name: values.name, model: values.model ?? null } },
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
  error,
  onCancel,
  onSubmit,
}: {
  title: string
  initial: Runner | null
  isPending: boolean
  /** The save mutation's error, owned by `RunnersPage` — the dialog stays open on failure and
   * this is where the Hub's own sentence is read. */
  error: unknown
  onCancel: () => void
  onSubmit: (values: RunnerFormValues) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [cli, setCli] = useState<RunnerCli>(initial?.cli ?? 'claude')
  // '' is the unset model — the "Provider default" choice, a valid runner state, not a placeholder.
  const [model, setModel] = useState(initial?.model ?? '')
  const { data: catalog } = useModelCatalog()

  // Loading and failed both land here. An empty select would read as "this provider declares no
  // models" rather than "we do not know yet", so the control is disabled and says which it is.
  const catalogAvailable = !!catalog
  const declaredModels = catalog?.providers.find((p) => p.provider === cli)?.models ?? []

  // The runner's own stored model, kept as an offered and selected option when the catalog does not
  // list it — without it, opening a legacy runner would silently re-point it at whatever option came
  // first, and Save would destroy a working configuration.
  const storedModel = initial?.model ?? null
  const storedIsDeclared = declaredModels.some((m) => m.id === storedModel)
  const storedOption = storedModel && !storedIsDeclared ? storedModel : null

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{ background: 'var(--scrim)' }}
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="runner-form-title"
        className="lifted-surface surface-enter w-[min(448px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="runner-form-title" className="text-base font-medium mb-4" style={{ color: 'var(--text)' }}>
          {title}
        </h2>
        <div className="space-y-3">
          <div>
            <label htmlFor="runner-name" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Name
            </label>
            <Input
              id="runner-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm"
              placeholder="e.g. Claude Opus"
            />
          </div>
          <div>
            <label htmlFor="runner-cli" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              CLI
            </label>
            <Select
              id="runner-cli"
              value={cli}
              disabled={!!initial}
              onChange={(e) => {
                setCli(e.target.value as RunnerCli)
                // Back to unset, not to the new provider's default model: unset is a valid runner
                // state, and choosing a model on the operator's behalf is the same class of mistake
                // as silently re-pointing a legacy runner. AgentCreateDialog resets to a concrete
                // model id because an agent must have one; a runner must not.
                setModel('')
              }}
              className="px-3 py-2 text-sm capitalize"
            >
              {CLI_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="runner-model" className="block text-xs mb-1" style={{ color: 'var(--text-3)' }}>
              Model
            </label>
            <Select
              id="runner-model"
              value={model}
              disabled={!catalogAvailable}
              onChange={(e) => setModel(e.target.value)}
              className="px-3 py-2 text-sm"
            >
              <option value="">Provider default</option>
              {storedOption && (
                <option value={storedOption}>
                  {initial?.model_unrecognised ? `${storedOption} — unrecognised` : storedOption}
                </option>
              )}
              {declaredModels.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </Select>
            {!catalogAvailable && (
              <p className="text-xs mt-1" style={{ color: 'var(--text-3)' }}>
                The model catalog is unavailable — this runner will use the provider's default.
              </p>
            )}
          </div>
        </div>
        {!!error && (
          <div
            role="alert"
            className="mt-3 rounded-md px-3 py-2 text-xs"
            style={{ background: 'var(--error-cont)', color: 'var(--red)' }}
          >
            {readableApiError(error, 'The runner could not be saved.')}
          </div>
        )}
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
