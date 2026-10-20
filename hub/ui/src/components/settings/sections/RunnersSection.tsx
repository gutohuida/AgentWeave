import * as React from 'react'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useManagerJobs } from '@/api/manager'
import { useModelCatalog } from '@/api/modelCatalog'
import { useCreateRunner, useDeleteRunner, useRunners, useUpdateRunner, type Runner } from '@/api/runners'
import { PROVIDER_CLI, RunnerForm } from '@/components/runners/RunnerForm'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import { RunnersSettings } from '../RunnersSettings'

/** Project settings → Runners, on the Hub: the list, and the runner dialog for new and edit. */
export function RunnersSection() {
  const { data: runners, isLoading, error, refetch } = useRunners()
  const { data: catalog } = useModelCatalog()
  const { data: agents = [], error: agentsError } = useAgents()
  const { data: jobs, error: jobsError } = useManagerJobs()
  const createRunner = useCreateRunner()
  const updateRunner = useUpdateRunner()
  const deleteRunner = useDeleteRunner()
  const [creating, setCreating] = React.useState(false)
  const [editing, setEditing] = React.useState<Runner | null>(null)
  const [deleteError, setDeleteError] = React.useState<string | null>(null)

  // A failed read is said, with a Retry: never a skeleton that waits for an answer that is not
  // coming, and never rows that could be saved over settings that were never read.
  if (error && !runners) {
    return (
      <SettingsPage icon="terminal" title="Runners" description="Which CLI and model an agent launches with.">
        <SettingsNotice tone="error" title="The runners could not be read." action={{ label: 'Retry', onClick: () => void refetch() }}>
          <p>{readableApiError(error, 'The Hub did not return a reason.')}</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (isLoading || !runners) {
    return (
      <SettingsPage icon="terminal" title="Runners" description="Which CLI and model an agent launches with.">
        <SettingsLoading label="Loading runners" rows={3} />
      </SettingsPage>
    )
  }

  return (
    <>
      <RunnersSettings
        runners={runners}
        // An unrecognised model is shown as stored, with the list's own warning beside it.
        modelLabel={(runner) => (catalog && !runner.model_unrecognised ? runnerModelPart(runner, catalog) : null)}
        usedBy={(runner) =>
          agents.filter((agent) => agent.runner_id === runner.id).length +
          (jobs ?? []).filter((job) => job.runner_id === runner.id).length
        }
        deleting={deleteRunner.isPending}
        notices={
          <>
            {/* "Used by" is counted from these; unread, a count of 0 would be a false all-clear. */}
            {agentsError || jobsError ? (
              <SettingsNotice tone="warning" title="Who uses each runner could not be read." testId="runners-usage-error">
                <p>The counts below leave out {agentsError && jobsError ? 'agents and manager jobs' : agentsError ? 'agents' : 'manager jobs'}.</p>
              </SettingsNotice>
            ) : null}
            {deleteError ? (
              <SettingsNotice tone="error" title="The runner was not deleted.">
                <p>{deleteError}</p>
              </SettingsNotice>
            ) : null}
          </>
        }
        onNew={() => {
          // The mutations outlive the dialog, so a refusal from the last attempt would still be on
          // `createRunner.error` when this one opens.
          createRunner.reset()
          setCreating(true)
        }}
        onEdit={(runner) => {
          updateRunner.reset()
          setEditing(runner)
        }}
        onDelete={(runner) => {
          setDeleteError(null)
          deleteRunner.mutate(runner.id, {
            onSuccess: () => toast({ title: `${runner.name} deleted`, tone: 'success' }),
            onError: (error: unknown) => setDeleteError(readableApiError(error, 'Could not delete runner')),
          })
        }}
      />
      {creating ? (
        <RunnerForm
          title="New runner"
          initial={null}
          isPending={createRunner.isPending}
          error={createRunner.error}
          onCancel={() => {
            createRunner.reset()
            setCreating(false)
          }}
          onSubmit={(values) =>
            createRunner.mutate(values, {
              onSuccess: () => {
                setCreating(false)
                toast({ title: `${values.name} added`, tone: 'success' })
              },
            })
          }
        />
      ) : null}
      {editing ? (
        <RunnerForm
          title={`Edit ${editing.name}`}
          initial={editing}
          isPending={updateRunner.isPending}
          error={updateRunner.error}
          onCancel={() => {
            updateRunner.reset()
            setEditing(null)
          }}
          onSubmit={(values) =>
            updateRunner.mutate(
              // `model` is always sent on edit, `null` being the "Provider default" choice —
              // `undefined` would be dropped by JSON.stringify and read as "leave it alone". A
              // Copilot runner always sends its provider too, `null` when off: the Hub judges the
              // (provider, model) pair the edit leaves behind.
              {
                id: editing.id,
                updates: {
                  name: values.name,
                  model: values.model ?? null,
                  ...(editing.cli === PROVIDER_CLI ? { provider_config: values.provider_config ?? null } : {}),
                },
              },
              {
                onSuccess: () => {
                  setEditing(null)
                  toast({ title: `${values.name} saved`, tone: 'success' })
                },
              },
            )
          }
        />
      ) : null}
    </>
  )
}
