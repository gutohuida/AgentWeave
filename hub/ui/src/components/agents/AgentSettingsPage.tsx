import * as React from 'react'
import {
  AgentSummary,
  MAX_AGENT_DESCRIPTION_CHARS,
  useAgentLaunchability,
  useAgents,
  useAgentSessions,
  useArchiveAgent,
  useUpdateAgentCheckpointMode,
  useUpdateAgentCheckpointOverride,
  useUpdateAgentDescription,
  useUpdateAgentGithubMcp,
  useUpdateAgentGrant,
  useUpdateAgentPermissionDefault,
  useUpdateAgentPool,
  useUpdateAgentReachGrants,
  useUpdateAgentReviewAgents,
} from '@/api/agents'
import { ApiError, readableApiError } from '@/api/client'
import { useBindAgentCharter, useCharters } from '@/api/charters'
import { permissionModeValues, useModelCatalog } from '@/api/modelCatalog'
import { useProjectSettings } from '@/api/projects'
import { useBindAgentModel, useProviderLaunchability, useRunners, useUpdateAgentWaiting } from '@/api/runners'
import type { AgentPoolEntry, PoolEntryWrite } from '@/api/agentPool'
import { PoolEditor } from './pool/PoolEditor'
import { entryLabel } from './pool/poolModel'
import { Button } from '@/components/ui/button'
import { SettingsLoading, SettingsNotice, SettingsPage } from '@/components/ui/settings'
import { landOnSetting } from '@/components/settings/landOnSetting'
import { runnerCeilingNote } from '@/components/environment/describeThreshold'
import { useAgentWorkspace } from '@/api/workspace'
import { useCopy } from '@/hooks/useCopy'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import { FoldAgentDialog } from '@/components/agents/FoldAgentDialog'
import { AgentIdentitySettings, type AgentPatch } from './settings/AgentSettingsSections'
import { AgentRunsPage } from './settings/AgentRunsPage'
import {
  AgentCharterGroup,
  AgentCheckpointsSettings,
  AgentCopilotGroup,
  AgentPermissionsSettings,
  AgentRunningSettings,
  AgentWorkspaceSettings,
  type ModelChoice,
} from './settings/AgentSettingsPages'
import { agentDestination, environmentDestination, goTo, type AgentSettingsSection } from '@/lib/navigation'
import { useProjectCheckpoints } from '@/api/checkpoints'
import { CheckpointsPanelContainer } from '@/components/checkpoints/CheckpointsPanelContainer'
import { useConfigStore } from '@/store/configStore'
import { PERMISSION_WAIT_FALLBACK_SECONDS, QUESTION_WAIT_FALLBACK_SECONDS } from '@/lib/agentWaits'

interface AgentSettingsPageProps {
  agent: string
  section: AgentSettingsSection
  /** The setting the location names, to land on. */
  setting?: string | null
}

/**
 * One section of a profile's settings, as the open tab of the profile's page (FR-13, FR-14): the
 * page's tabs choose the section, so there is no section list, back link or search here. The
 * profile's page is the only place these settings are shown.
 *
 * Six sections (Profile, Models, Permissions, Checkpoints, Workspace, and Runs, which lists what
 * it has run), every setting applying on change with a toast. Retired section ids are resolved to
 * these before they get here (`resolveAgentSettingsSection`).
 */
export function AgentSettingsPage({ agent, section, setting }: AgentSettingsPageProps) {
  // `all`, not the default open roster: an archived agent must still resolve here, because this
  // is the only surface that can unarchive it.
  const { data: roster = [], isLoading } = useAgents('all')
  const summary = roster.find((candidate) => candidate.name === agent) ?? null
  const rootRef = React.useRef<HTMLDivElement>(null)
  const ready = Boolean(summary)
  React.useEffect(() => {
    if (!setting || !ready || !rootRef.current) return
    return landOnSetting(rootRef.current, setting)
  }, [setting, section, agent, ready])

  if (isLoading) {
    return (
      <div className="aw-settings-page" aria-label="Loading profile settings">
        <SettingsLoading label="Loading profile settings" rows={3} />
      </div>
    )
  }
  if (!summary) return <Shell>This profile is no longer in the roster.</Shell>
  return (
    <div className="min-w-0" data-testid={`agent-settings-${section}`} ref={rootRef}>
      <SectionContent agent={summary} section={section} />
    </div>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="aw-settings-page text-xs" style={{ color: 'var(--text-3)' }} data-testid="agent-settings-empty">
      {children}
    </div>
  )
}

type Mutation<V> = { mutate: (vars: V, options: { onSuccess: () => void; onError: (e: unknown) => void }) => void }

/** One field's write: the mutation that owns it and what it is sent. */
type Write = [Mutation<never>, unknown]

/**
 * Applies a patch as the writes a section names (each field has its own route), says so in a
 * toast, and keeps the last refusal for the page to show.
 *
 * `mutate` with callbacks rather than `mutateAsync`, so each write keeps its hook's own
 * invalidation. Each section builds only the mutations it uses.
 */
function usePatchWrites() {
  const [refusal, setRefusal] = React.useState<string | null>(null)
  const run = (writes: Write[], said: string) => {
    setRefusal(null)
    Promise.all(
      writes.map(
        ([mutation, vars]) =>
          new Promise((resolve, reject) =>
            (mutation as Mutation<unknown>).mutate(vars, { onSuccess: () => resolve(undefined), onError: reject }),
          ),
      ),
    ).then(
      () => toast({ title: said, tone: 'success' }),
      (error: unknown) => {
        const reason = readableApiError(error, 'The Hub did not return a reason.')
        setRefusal(reason)
        toast({ title: 'Not saved', description: reason, tone: 'error' })
      },
    )
  }
  const notices = refusal ? (
    <SettingsNotice tone="error" title="That change was not saved.">
      <p>{refusal}</p>
    </SettingsNotice>
  ) : null
  return { run, notices }
}

const w = <V,>(mutation: Mutation<V>, vars: V): Write => [mutation as unknown as Mutation<never>, vars]

/** The model its runner gives it, as the menu's value; null with no runner bound. */
function currentModel(agent: AgentSummary, runners: ReturnType<typeof useRunners>['data']): ModelChoice | null {
  const runner = (runners ?? []).find((candidate) => candidate.id === agent.runner_id)
  return runner ? { provider: runner.cli, model: runner.model ?? null } : null
}

function AgentSection({ agent }: { agent: AgentSummary }) {
  const description = useUpdateAgentDescription()
  const bindCharter = useBindAgentCharter()
  const { data: charters = [], error: chartersError } = useCharters()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { run: write, notices } = usePatchWrites()
  const apply = (patch: AgentPatch, said: string) => {
    const writes: Write[] = []
    if ('description' in patch) writes.push(w(description, { agent: agent.name, description: patch.description ?? null }))
    if ('charter_id' in patch) writes.push(w(bindCharter, { agent: agent.name, charterId: patch.charter_id ?? null }))
    write(writes, said)
  }
  const archive = useArchiveAgent()
  const queueRefusal = archive.error instanceof ApiError ? parseQueueArchiveRefusal(archive.error) : null
  const refusal =
    archive.error instanceof ApiError ? (queueRefusal?.message ?? archive.error.message) : archive.error ? 'Could not save.' : null
  const run = (archived: boolean, discardQueueEntryIds?: string[]) =>
    archive.mutate(
      { agent: agent.name, archived, discardQueueEntryIds },
      { onSuccess: () => toast({ title: archived ? `${agent.name} archived` : `${agent.name} is back`, tone: 'success' }) },
    )

  return (
    <AgentIdentitySettings
      agent={agent}
      notices={notices}
      now={new Date()}
      descriptionMax={MAX_AGENT_DESCRIPTION_CHARS}
      archiving={archive.isPending}
      foldAction={<FoldAgentDialog agent={agent.name} />}
      onChange={apply}
      onArchive={() => run(true)}
      onUnarchive={() => run(false)}
      archiveRefusal={
        refusal ? (
          // Archiving is refused, with the reason, while a run is in progress or messages are
          // undelivered: the refusal is the operator's next instruction, not a failure.
          <>
            <p>{refusal}</p>
            {queueRefusal ? (
              <Button variant="destructive" size="sm" disabled={archive.isPending} onClick={() => run(true, queueRefusal.ids)}>
                Discard {queueRefusal.ids.length} queued message{queueRefusal.ids.length === 1 ? '' : 's'} and archive — cannot be undone
              </Button>
            ) : null}
          </>
        ) : undefined
      }
    >
      {chartersError ? <span className="aw-row-note" role="status">Could not load the charters, so the list is incomplete.</span> : null}
      <AgentCharterGroup
        agent={agent}
        charters={charters.map((charter) => ({ value: charter.id, label: charter.name }))}
        onChange={apply}
        onOpenCharters={projectId ? () => goTo(environmentDestination(projectId, 'charters')) : undefined}
      />
    </AgentIdentitySettings>
  )
}

function RunningSection({ agent }: { agent: AgentSummary }) {
  const bindModel = useBindAgentModel()
  const waiting = useUpdateAgentWaiting()
  const reviewAgents = useUpdateAgentReviewAgents()
  const githubMcp = useUpdateAgentGithubMcp()
  const { run, notices } = usePatchWrites()
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const { data: providerLaunch, error: providerLaunchError } = useProviderLaunchability()
  const { data: launchability, error: launchabilityError } = useAgentLaunchability()
  const model = currentModel(agent, runners)
  const verdict = launchability?.agents[agent.name]
  const cannotRun = verdict?.runnable === false
  // The Hub judges collaboration only for a runnable agent, so the two lines never meet (F178).
  const cannotCollaborate = verdict?.runnable === true && verdict.collaboration_ready === false

  // Every model of every provider whose coding agent is installed, and each provider's own default.
  // What the agent runs on now is always listed, installed or not, so the menu can show it.
  const installed = (provider: string) => providerLaunch?.providers[provider]?.present !== false
  const modelOptions = (catalog?.providers ?? []).flatMap((provider) =>
    installed(provider.provider) || model?.provider === provider.provider
      ? [
          { value: `${provider.provider}:`, label: `${provider.label} · its default`, detail: 'Whatever the provider picks' },
          ...provider.models.map((entry) => ({ value: `${provider.provider}:${entry.id}`, label: `${provider.label} · ${entry.label}` })),
        ]
      : [],
  )
  const currentValue = model ? `${model.provider}:${model.model ?? ''}` : ''
  if (model && !modelOptions.some((option) => option.value === currentValue)) {
    const runner = runners.find((candidate) => candidate.id === agent.runner_id)
    modelOptions.push({
      value: currentValue,
      label: runner ? `${runner.cli} · ${runnerModelPart(runner, catalog)}` : currentValue,
      detail: 'Not in the model catalog',
    })
  }

  const notes = (
    <>
      {!agent.runner_id && !verdict ? <span className="aw-control-warning" role="status">This profile cannot run until it has a model.</span> : null}
      {cannotRun ? (
        <span className="aw-control-warning" role="status">
          This profile cannot run: {verdict.reason ?? 'the Hub reports it as not runnable.'}
        </span>
      ) : null}
      {cannotCollaborate ? (
        <span className="aw-control-warning" role="status">
          This profile will run, but cannot collaborate: {verdict.collaboration_reason ?? 'the Hub reports its tool calls would be refused.'}
        </span>
      ) : null}
      {!verdict && launchabilityError ? <span className="aw-row-note" role="status">Could not check whether this profile can run.</span> : null}
      {providerLaunchError ? <span className="aw-row-note" role="status">Could not check which coding agents are installed; every provider is listed.</span> : null}
      {catalogError ? <span className="aw-row-note" role="status">Could not load the model catalog; the list of models is incomplete.</span> : null}
      {/* An empty list here would read as "no model is bound". */}
      {runnersError ? (
        <span className="aw-control-warning" role="alert" data-testid="agent-runners-error">
          Could not load this project's runners, so the model shown may be wrong.
        </span>
      ) : null}
    </>
  )

  const updatePool = useUpdateAgentPool()
  const [poolError, setPoolError] = React.useState<string | null>(null)
  const current = agent.pool ?? []
  const asWrite = (entry: Pick<AgentPoolEntry, 'runner_id' | 'effort' | 'default'>) => ({
    runner_id: entry.runner_id,
    effort: entry.effort,
    default: entry.default,
  })
  // The Hub applies the whole list or none of it; its refusal is shown where the change was asked for.
  const writePool = (next: PoolEntryWrite[], said: string) => {
    setPoolError(null)
    updatePool.mutate(
      { agent: agent.name, pool: next },
      {
        onSuccess: () => toast({ title: said, tone: 'success' }),
        onError: (error: unknown) => setPoolError(readableApiError(error, 'The Hub did not return a reason.')),
      },
    )
  }
  const poolLabel = (entry: Pick<AgentPoolEntry, 'cli' | 'model' | 'effort'>) => entryLabel(catalog, entry)

  return (
    <AgentRunningSettings
      agent={agent}
      pool={
        agent.pool ? (
          <PoolEditor
            agentName={agent.name}
            pool={current}
            catalog={catalog}
            error={poolError}
            pending={updatePool.isPending}
            onAdd={(choice) =>
              // Named by model: the Hub uses the project's runner for it, or makes one (FR-2).
              writePool(
                [...current.map(asWrite), { ...choice, default: current.length === 0 }],
                `${agent.name} may run on ${poolLabel({ cli: choice.provider, model: choice.model, effort: choice.effort })}`,
              )
            }
            onRemove={(entry) =>
              writePool(current.filter((e) => e.id !== entry.id).map(asWrite), `${agent.name} no longer runs on ${poolLabel(entry)}`)
            }
            onMakeDefault={(entry) =>
              writePool(
                current.map((e) => ({ ...asWrite(e), default: e.id === entry.id })),
                `${agent.name} runs on ${poolLabel(entry)} unless a task chooses another`,
              )
            }
          />
        ) : undefined
      }
      model={model}
      modelOptions={modelOptions}
      runNotes={notes}
      permissionFallback={PERMISSION_WAIT_FALLBACK_SECONDS}
      questionFallback={QUESTION_WAIT_FALLBACK_SECONDS}
      notices={notices}
      onModelChange={(choice, said) => run([w(bindModel, { agent: agent.name, provider: choice.provider, model: choice.model })], said)}
      onChange={(patch, said) =>
        run(
          (['permission_timeout_seconds', 'question_timeout_seconds'] as const)
            .filter((field) => field in patch)
            .map((field) => w(waiting, { agent: agent.name, field, seconds: patch[field] ?? null })),
          said,
        )
      }
    >
      {agent.runner === 'copilot' || model?.provider === 'copilot' ? (
        <AgentCopilotGroup
          agent={agent}
          onReviewAgents={(agents, said) => run([w(reviewAgents, { agent: agent.name, agents })], said)}
          onGithubMcp={(enabled, said) => run([w(githubMcp, { agent: agent.name, enabled })], said)}
        />
      ) : null}
    </AgentRunningSettings>
  )
}

function PermissionsSection({ agent }: { agent: AgentSummary }) {
  const permission = useUpdateAgentPermissionDefault()
  const reach = useUpdateAgentReachGrants()
  const grant = useUpdateAgentGrant()
  const { run, notices } = usePatchWrites()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const options = permissionModeValues(catalog)
  const apply = (patch: AgentPatch, said: string) => {
    const name = agent.name
    const writes: Write[] = []
    if ('default_permission_mode' in patch) writes.push(w(permission, { agent: name, mode: patch.default_permission_mode ?? null }))
    if ('reach_grants' in patch) writes.push(w(reach, { agent: name, grants: patch.reach_grants ?? null }))
    for (const key of ['can_read_checkpoints', 'can_recall', 'can_accept_evidence', 'can_admin_specs'] as const) {
      if (key in patch) writes.push(w(grant, { agent: name, grant: key, enabled: Boolean(patch[key]) }))
    }
    run(writes, said)
  }
  // What clearing the default gives this agent's run, as the Hub computes it.
  const builtIn = agent.permission_mode_built_in
  const builtInLabel = builtIn ? (options.find((option) => option.id === builtIn)?.label ?? builtIn) : 'depends on the runner'
  return (
    <AgentPermissionsSettings
      agent={agent}
      permissionModes={options}
      permissionUnset={{
        label: `${agent.permission_mode_from_project ? 'Project default' : 'Built-in default'} (${builtInLabel})`,
        detail: 'What a run gets when neither its thread nor this profile has chosen.',
      }}
      projectGrants={agent.project_reach_grants ?? null}
      permissionNote={
        agent.default_permission_mode === 'manual' && agent.runner === 'claude' ? (
          // F453: Claude's CLI approves commands it judges read-only before the Hub is asked.
          <span className="aw-row-note" data-testid="ask-me-readonly-note">
            Claude Code still runs commands it treats as read-only (such as <code>echo</code> or <code>git status</code>) without asking; writes and other commands come to you.
          </span>
        ) : catalogError ? (
          <span className="aw-row-note" role="status">Could not load the permission modes, so the list is incomplete.</span>
        ) : null
      }
      notices={notices}
      onChange={apply}
    />
  )
}

function CheckpointsSection({ agent }: { agent: AgentSummary }) {
  // The profile's own checkpoints are read here, on its page (leaner-navigation FR-9): the list,
  // then one opened in place with a way back. The same query the list reads, so the count is free.
  const [openedCheckpoint, setOpenedCheckpoint] = React.useState<string | null>(null)
  const { data: takenData, error: takenError } = useProjectCheckpoints({ agent: agent.name })
  const mode = useUpdateAgentCheckpointMode()
  const threshold = useUpdateAgentCheckpointOverride()
  const { run, notices } = usePatchWrites()
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const { data: projectSettings, isError: projectSettingsFailed } = useProjectSettings(projectId ?? null)
  const project = {
    mode: projectSettings?.checkpoint_mode ?? 'offered',
    at:
      projectSettings?.checkpoint_threshold_value != null
        ? `${projectSettings.checkpoint_threshold_value}${projectSettings.checkpoint_threshold_mode === 'tokens' ? ' tokens' : '%'}`
        : null,
  } as const
  // Where the checkpoint actually fires: the agent's own point, else the project's.
  const hasOwn = agent.checkpoint_threshold_value != null
  const ceiling = runnerCeilingNote(
    agent.checkpoint_compaction_percent,
    hasOwn ? agent.checkpoint_threshold_mode : projectSettings?.checkpoint_threshold_mode,
    hasOwn ? agent.checkpoint_threshold_value : projectSettings?.checkpoint_threshold_value,
    agent.runner,
  )
  return (
    <AgentCheckpointsSettings
      agent={agent}
      project={project}
      note={
        ceiling ??
        (!hasOwn && projectSettingsFailed
          ? 'The project’s threshold could not be read, so where this profile’s checkpoint fires is not shown.'
          : null)
      }
      notices={notices}
      onChange={(patch, said) => {
        const writes: Write[] = []
        if ('checkpoint_mode' in patch) writes.push(w(mode, { agent: agent.name, mode: patch.checkpoint_mode ?? null }))
        if ('checkpoint_threshold_value' in patch) {
          writes.push(
            w(threshold, {
              agent: agent.name,
              mode: patch.checkpoint_threshold_mode ?? null,
              value: patch.checkpoint_threshold_value ?? null,
              notes: null,
            }),
          )
        }
        run(writes, said)
      }}
      // A failed read shows no count rather than a false 0; the list below names the failure.
      taken={takenError ? undefined : takenData?.checkpoints.length}
      list={
        <CheckpointsPanelContainer
          scope={{ agent: agent.name }}
          openedId={openedCheckpoint}
          onOpen={setOpenedCheckpoint}
          onOpenConversation={(owner, conversationId) => {
            if (projectId) goTo(agentDestination(projectId, owner, conversationId))
          }}
          emptyText={`No checkpoint has been taken in ${agent.name}'s threads yet.`}
        />
      }
    />
  )
}

function WorkspaceSection({ agent }: { agent: AgentSummary }) {
  const { data, isLoading, error } = useAgentWorkspace(agent.name)
  const { data: sessionData } = useAgentSessions(agent.name)
  const { copy } = useCopy()
  const now = React.useMemo(() => new Date(), [])
  if (isLoading || !data) {
    return (
      <SettingsPage icon="folder" title="Workspace" description={`Where ${agent.name} does its work on disk.`}>
        {isLoading ? (
          <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading…</span>
        ) : (
          <span className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
            {error instanceof ApiError ? error.message : 'The project workspace is unavailable.'}
          </span>
        )}
      </SettingsPage>
    )
  }
  return (
    <AgentWorkspaceSettings
      agent={agent}
      workingDir={data.working_dir}
      isolated={data.isolated}
      branch={data.branch}
      provisioned={data.provisioned}
      note={data.unavailable_reason}
      taskCheckouts={data.task_checkouts ?? []}
      sessions={sessionData?.sessions ?? []}
      now={now}
      onCopy={(text, said) => {
        copy(text)
        toast({ title: said, tone: 'success' })
      }}
    />
  )
}

function SectionContent({ agent, section }: { agent: AgentSummary; section: AgentSettingsSection }) {
  switch (section) {
    case 'agent':
      return <AgentSection agent={agent} />
    case 'running':
      return <RunningSection agent={agent} />
    case 'permissions':
      return <PermissionsSection agent={agent} />
    case 'checkpoints':
      return <CheckpointsSection agent={agent} />
    case 'workspace':
      return <WorkspaceSection agent={agent} />
    case 'runs':
      return <AgentRunsPage agent={agent.name} />
  }
}

function parseQueueArchiveRefusal(error: ApiError): { message: string; ids: string[] } | null {
  try {
    const detail = (JSON.parse(error.message) as { detail?: unknown }).detail
    if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return null
    const value = detail as { message?: unknown; blocking_queue_entry_ids?: unknown }
    if (typeof value.message !== 'string' || !Array.isArray(value.blocking_queue_entry_ids)) return null
    const ids = value.blocking_queue_entry_ids.filter((id): id is string => typeof id === 'string')
    return ids.length ? { message: value.message, ids } : null
  } catch {
    return null
  }
}
