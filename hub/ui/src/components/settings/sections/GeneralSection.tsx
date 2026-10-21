import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import {
  useMainBranchSuggestion,
  useProjectSettings,
  useProjects,
  useRelocateProject,
  useUpdateProjectSettings,
  type ProjectSettings,
} from '@/api/projects'
import { permissionModeValues, resolveCatalogModel, useModelCatalog, type ModelCatalogResponse } from '@/api/modelCatalog'
import { useRunners, type Runner } from '@/api/runners'
import { DeleteProjectDialog } from '@/components/environment/DeleteProjectDialog'
import { projectCeilingNotes } from '@/components/environment/describeThreshold'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { GeneralSettings } from '../GeneralSettings'
import { catalogModelOptions, runnerChoiceOptions } from '../settingsOptions'

/** Project settings → General, on the Hub. Each change is its own save, sending only the fields
 *  it changed (the route merges onto what is stored), so a change made in another section since
 *  this page loaded is never written back over. */
/** Whether *runner*'s CLI declares *model*, by id or alias: the Hub checks `checkpoint_model` against
 *  the runner's own CLI and refuses one it does not declare (F807). No catalog yet means no
 *  evidence either way, so nothing is dropped. */
function runnerDeclaresModel(
  runner: Runner | undefined,
  catalog: ModelCatalogResponse | undefined,
  model: string | null,
): boolean {
  if (!model || !runner || !catalog) return true
  const entry = catalog.providers.find((provider) => provider.provider === runner.cli)
  return resolveCatalogModel(entry, model) !== null
}

export function GeneralSection({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projects = [], error: projectsError, refetch: refetchProjects } = useProjects()
  const project = projects.find((item) => item.id === projectId)
  const { data: settings, error: readError, refetch } = useProjectSettings(projectId ?? null)
  const { data: mainBranch } = useMainBranchSuggestion(projectId ?? null)
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: agents = [], isError: agentsFailed } = useAgents()
  const { data: catalog } = useModelCatalog()
  const update = useUpdateProjectSettings(projectId ?? '')
  const relocate = useRelocateProject(projectId ?? '')
  // Shown at once, before the Hub answers, so a switch does not snap back while its save is in
  // flight; dropped when the save settles (the cache then holds what is stored).
  const [pending, setPending] = React.useState<Partial<ProjectSettings>>({})
  const [warnings, setWarnings] = React.useState<string[]>([])
  const [refusal, setRefusal] = React.useState<string | null>(null)
  const [deleting, setDeleting] = React.useState(false)

  // The project itself unread is the same failure: the rows would wait on it forever.
  const failedRead = (!settings && readError) || (!project && projectsError) || null
  if (failedRead) {
    // A failed read is not a slow one, and the rows stay hidden: nothing can be saved over
    // settings that were never read.
    return (
      <SettingsPage icon="settings" title="General" description="How agents work together in this project, what they may reach, and where approved work lands.">
        <SettingsNotice
          tone="error"
          title="This project's settings could not be loaded."
          action={{ label: 'Retry', onClick: () => void Promise.all([refetch(), refetchProjects()]) }}
        >
          <p>{readableApiError(failedRead, 'The Hub did not return a reason.')}</p>
          <p>Nothing stored has been changed.</p>
        </SettingsNotice>
      </SettingsPage>
    )
  }
  if (!settings || !project) {
    return (
      <SettingsPage icon="settings" title="General" description="How agents work together in this project, what they may reach, and where approved work lands.">
        <SettingsLoading label="Loading project settings" rows={5} />
      </SettingsPage>
    )
  }

  const shown: ProjectSettings = { ...settings, ...pending }
  const save = (patch: Partial<ProjectSettings>, said: string) => {
    setPending((current) => ({ ...current, ...patch }))
    setRefusal(null)
    update.mutate(patch, {
      onSuccess: (saved) => {
        // Saved, but worth knowing (warn, not refuse): F728's agent budget below the open agents,
        // F541's token threshold an agent can never reach.
        const savedWarnings = saved.warnings ?? []
        setWarnings(savedWarnings)
        toast({ title: said, tone: 'success', description: savedWarnings.length ? 'Saved, with a warning below.' : undefined })
      },
      onError: (error) => {
        const reason = readableApiError(error, 'The Hub did not return a reason.')
        setRefusal(reason)
        toast({ title: 'Not saved', description: reason, tone: 'error' })
      },
      onSettled: () =>
        setPending((current) => {
          const next = { ...current }
          for (const key of Object.keys(patch) as Array<keyof ProjectSettings>) delete next[key]
          return next
        }),
    })
  }

  // The model menu lists the chosen runner's CLI's models only, so a stored model that CLI does not
  // declare would stay unseen and the switch would be refused naming it (F807): clear it with the switch.
  const saveSetting = (patch: Partial<ProjectSettings>, said: string) => {
    if ('checkpoint_runner_id' in patch && !('checkpoint_model' in patch)) {
      const nextRunner = runners.find((runner) => runner.id === patch.checkpoint_runner_id)
      if (!runnerDeclaresModel(nextRunner, catalog, shown.checkpoint_model)) patch = { ...patch, checkpoint_model: null }
    }
    save(patch, said)
  }

  const checkpointRunner = runners.find((runner) => runner.id === shown.checkpoint_runner_id)
  const checkpointProvider = catalog?.providers.find((provider) => provider.provider === checkpointRunner?.cli)
  const contextWindow = resolveCatalogModel(checkpointProvider, shown.checkpoint_model)?.context_window ?? null

  return (
    <>
      <GeneralSettings
        settings={shown}
        runnerOptions={runnerChoiceOptions(
          runners,
          { label: 'None', detail: 'Checkpointing stays off until a runner is chosen' },
          // F268: the model a choice runs on, which is the project's checkpoint model when set.
          (runner) =>
            runnerModelPart(runner, catalog, {
              model: runnerDeclaresModel(runner, catalog, shown.checkpoint_model) ? shown.checkpoint_model : null,
            }),
        )}
        modelOptions={catalogModelOptions(checkpointProvider?.models ?? [], { stored: shown.checkpoint_model })}
        permissionModes={permissionModeValues(catalog)}
        folder={project.path_display ?? project.working_directory ?? ''}
        folderAvailable={project.directory_state === 'available'}
        mainBranch={mainBranch ?? null}
        contextWindow={contextWindow}
        ceilingNotes={projectCeilingNotes(settings.checkpoint_threshold_mode, settings.checkpoint_threshold_value, agents)}
        agentsUnreadable={agentsFailed}
        relocating={relocate.isPending}
        notices={
          <>
            {/* The checkpoint runner menu below would otherwise offer no runners, as if none existed. */}
            {runnersError ? (
              <SettingsNotice tone="warning" title="This project's runners could not be read." testId="settings-runners-error">
                <p>The checkpoint runner cannot be changed until they are. {readableApiError(runnersError, '')}</p>
              </SettingsNotice>
            ) : null}
            {refusal ? (
              <SettingsNotice tone="error" title="That change was not saved." testId="settings-save-refusal">
                <p>{refusal}</p>
              </SettingsNotice>
            ) : null}
            {warnings.length ? (
              <SettingsNotice tone="warning" title="Saved, but worth knowing" testId="settings-save-warnings">
                <ul>
                  {warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </SettingsNotice>
            ) : null}
            {relocate.isError ? (
              <SettingsNotice tone="error" title="The folder was not located.">
                <p>{readableApiError(relocate.error, 'The Hub did not return a reason.')}</p>
              </SettingsNotice>
            ) : null}
          </>
        }
        onChange={saveSetting}
        onRelocate={(path) =>
          relocate.mutate(
            { path },
            { onSuccess: () => toast({ title: 'Project folder updated', tone: 'success' }) },
          )
        }
        onOpenBudgets={onNavigate ? () => onNavigate('budgets') : undefined}
        onDeleteProject={() => setDeleting(true)}
      />
      <DeleteProjectDialog project={deleting ? project : null} onClose={() => setDeleting(false)} onDeleted={() => setDeleting(false)} />
    </>
  )
}
