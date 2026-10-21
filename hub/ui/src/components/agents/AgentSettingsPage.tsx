import * as React from 'react'
import { formatDistanceToNow } from 'date-fns'
import {
  AgentSummary,
  MAX_AGENT_DESCRIPTION_CHARS,
  useAgentLaunchability,
  useAgents,
  useAgentSessions,
  useArchiveAgent,
  useUpdateAgentDescription,
  useUpdateAgentGrant,
  useUpdateAgentPermissionDefault,
  useUpdateAgentReachGrants,
} from '@/api/agents'
import { ApiError, readableApiError } from '@/api/client'
import { permissionModeValues, useModelCatalog } from '@/api/modelCatalog'
import { useBindAgentRunner, useRunners } from '@/api/runners'
import { Button } from '@/components/ui/button'
import { SettingsGroup, SettingsLoading, SettingsNotice, SettingsRow as GridRow } from '@/components/ui/settings'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { SettingsNavLayout } from '@/components/settings/SettingsNavLayout'
import { runnerChoiceOptions } from '@/components/settings/settingsOptions'
import { useAgentWorkspace, type TaskCheckoutInfo } from '@/api/workspace'
import { useCopy } from '@/hooks/useCopy'
import { tint } from '@/lib/colorTint'
import { runnerModelPart } from '@/lib/runnerLabel'
import { toast } from '@/lib/toast'
import {
  CharterPicker,
  CheckpointOverrideSetting,
  CopilotGithubMcpSetting,
  CopilotReviewAgentsSetting,
  WaitingSetting,
} from './AgentSettingsControls'
import {
  AgentAccessSettings,
  AgentExecutionSettings,
  AgentIdentitySettings,
  type AgentPatch,
} from './settings/AgentSettingsSections'
import type { AgentSettingsSection } from '@/lib/navigation'
import { hubDate } from '@/lib/hubTime'
import { PERMISSION_WAIT_FALLBACK_SECONDS, QUESTION_WAIT_FALLBACK_SECONDS } from '@/lib/agentWaits'

interface AgentSettingsPageProps {
  agent: string
  section: AgentSettingsSection
  onSelectSection: (section: AgentSettingsSection) => void
  /** Where the back control goes: the agent's conversations (the caller decides which). */
  onBack: () => void
}

const SECTIONS: ReadonlyArray<{ id: AgentSettingsSection; label: string; icon: string }> = [
  { id: 'identity', label: 'Identity', icon: 'badge' },
  { id: 'execution', label: 'Execution', icon: 'terminal' },
  { id: 'charter', label: 'Charter', icon: 'menu_book' },
  { id: 'interaction', label: 'Interaction', icon: 'forum' },
  { id: 'context', label: 'Context', icon: 'memory' },
  { id: 'access', label: 'Access', icon: 'lock' },
  { id: 'workspace', label: 'Workspace', icon: 'folder' },
]

/**
 * An agent's configuration, as a destination rather than a dialog: its own section list and a way
 * back to its conversations, inside the content area (the app's rail stays put).
 *
 * Identity, Execution and Access are on the settings grid and apply on change with a toast;
 * Charter, Interaction, Context and Workspace keep their controls, framed the same way.
 */
export function AgentSettingsPage({ agent, section, onSelectSection, onBack }: AgentSettingsPageProps) {
  // `all`, not the default open roster: an archived agent must still resolve here, because this
  // is the only surface that can unarchive it.
  const { data: roster = [], isLoading } = useAgents('all')
  const { data: runners = [] } = useRunners()
  const summary = roster.find((candidate) => candidate.name === agent) ?? null
  const runnerName = summary?.runner_id ? runners.find((runner) => runner.id === summary.runner_id)?.name : null

  let body: React.ReactNode
  if (isLoading) {
    body = (
      <div className="aw-settings-page" aria-label="Loading agent settings">
        <SettingsLoading label="Loading agent settings" rows={3} />
      </div>
    )
  } else if (!summary) {
    body = <Shell>This agent is no longer in the roster.</Shell>
  } else {
    body = (
      <div className="min-w-0" data-testid={`agent-settings-${section}`}>
        <SectionContent agent={summary} section={section} />
      </div>
    )
  }

  return (
    <div className="h-full min-h-0">
      <SettingsNavLayout
        title={`${agent} settings`}
        subtitle={summary ? (runnerName ?? (summary.runner_id ? undefined : 'No runner')) : undefined}
        back={{ label: `Back to ${agent}`, onClick: onBack }}
        items={SECTIONS}
        active={section}
        onSelect={onSelectSection}
      >
        {body}
      </SettingsNavLayout>
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

function IdentitySection({ agent }: { agent: AgentSummary }) {
  const description = useUpdateAgentDescription()
  const { run: write, notices } = usePatchWrites()
  const apply = (patch: AgentPatch, said: string) =>
    write('description' in patch ? [w(description, { agent: agent.name, description: patch.description ?? null })] : [], said)
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
    <>
      <AgentIdentitySettings
        agent={agent}
        notices={notices}
        now={new Date()}
        descriptionMax={MAX_AGENT_DESCRIPTION_CHARS}
        archiving={archive.isPending}
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
      />
    </>
  )
}

function ExecutionSection({ agent }: { agent: AgentSummary }) {
  const runner = useBindAgentRunner()
  const permission = useUpdateAgentPermissionDefault()
  const reach = useUpdateAgentReachGrants()
  const { run, notices } = usePatchWrites()
  const apply = (patch: AgentPatch, said: string) => {
    const name = agent.name
    const writes: Write[] = []
    if ('runner_id' in patch) writes.push(w(runner, { agent: name, runnerId: patch.runner_id ?? null }))
    if ('default_permission_mode' in patch) writes.push(w(permission, { agent: name, mode: patch.default_permission_mode ?? null }))
    if ('reach_grants' in patch) writes.push(w(reach, { agent: name, grants: patch.reach_grants ?? null }))
    run(writes, said)
  }
  const { data: runners = [], error: runnersError } = useRunners()
  const { data: catalog, error: catalogError } = useModelCatalog()
  const { data: launchability, error: launchabilityError } = useAgentLaunchability()
  const options = permissionModeValues(catalog)
  const verdict = launchability?.agents[agent.name]
  const cannotRun = verdict?.runnable === false
  // The Hub judges collaboration only for a runnable agent, so the two lines never meet (F178).
  const cannotCollaborate = verdict?.runnable === true && verdict.collaboration_ready === false
  // What clearing the default gives this agent's run, as the Hub computes it.
  const builtIn = agent.permission_mode_built_in
  const builtInLabel = builtIn ? (options.find((option) => option.id === builtIn)?.label ?? builtIn) : 'depends on the runner'

  const runnerNotes = (
    <>
      {!agent.runner_id && !verdict ? <span className="aw-control-warning" role="status">This agent cannot run until it has a runner.</span> : null}
      {cannotRun ? (
        <span className="aw-control-warning" role="status">
          This agent cannot run: {verdict.reason ?? 'the Hub reports it as not runnable.'}
        </span>
      ) : null}
      {cannotCollaborate ? (
        <span className="aw-control-warning" role="status">
          This agent will run, but cannot collaborate: {verdict.collaboration_reason ?? 'the Hub reports its tool calls would be refused.'}
        </span>
      ) : null}
      {!verdict && launchabilityError ? <span className="aw-row-note" role="status">Could not check whether this agent can run.</span> : null}
      {catalogError ? <span className="aw-row-note" role="status">Could not load the model catalog; runners show plain model ids.</span> : null}
      {/* An empty runner list here would read as "this project has no runners". */}
      {runnersError ? (
        <span className="aw-control-warning" role="alert" data-testid="agent-runners-error">
          Could not load this project's runners, so the list below is incomplete.
        </span>
      ) : null}
    </>
  )

  return (
    <AgentExecutionSettings
      agent={agent}
      runners={runners}
      runnerOptions={runnerChoiceOptions(runners, { label: 'No runner', detail: 'The agent cannot run until it has one' }, (runner) => runnerModelPart(runner, catalog))}
      permissionModes={options}
      permissionUnset={{
        label: `${agent.permission_mode_from_project ? 'Project default' : 'Built-in default'} (${builtInLabel})`,
        detail: 'What a run gets when neither its conversation nor this agent has chosen.',
      }}
      projectGrants={agent.project_reach_grants ?? null}
      runnerNotes={runnerNotes}
      permissionNote={
        agent.default_permission_mode === 'manual' && agent.runner === 'claude' ? (
          // F453: Claude's CLI approves commands it judges read-only before the Hub is asked.
          <span className="aw-row-note" data-testid="ask-me-readonly-note">
            Claude Code still runs commands it treats as read-only (such as <code>echo</code> or <code>git status</code>) without asking; writes and other commands come to you.
          </span>
        ) : null
      }
      notices={notices}
      onChange={apply}
    >
      {agent.runner === 'copilot' ? (
        <SettingsGroup title="Copilot" description="Settings only a Copilot runner has.">
          <GridRow label="Review agents" description="Copilot's own built-in agents this agent may consult before recording a review verdict." stacked control={<CopilotReviewAgentsSetting agent={agent} />} />
          <GridRow label="GitHub server" description="Copilot's own built-in GitHub MCP server for this agent." stacked control={<CopilotGithubMcpSetting agent={agent} />} />
        </SettingsGroup>
      ) : null}
    </AgentExecutionSettings>
  )
}

function AccessSection({ agent }: { agent: AgentSummary }) {
  const grant = useUpdateAgentGrant()
  const { run, notices } = usePatchWrites()
  const apply = (patch: AgentPatch, said: string) =>
    run(
      (['can_read_checkpoints', 'can_recall', 'can_accept_evidence'] as const)
        .filter((key) => key in patch)
        .map((key) => w(grant, { agent: agent.name, grant: key, enabled: Boolean(patch[key]) })),
      said,
    )
  return <AgentAccessSettings agent={agent} onChange={apply} notices={notices} />
}

function SectionContent({ agent, section }: { agent: AgentSummary; section: AgentSettingsSection }) {
  switch (section) {
    case 'identity':
      return <IdentitySection agent={agent} />

    case 'execution':
      return <ExecutionSection agent={agent} />

    case 'charter':
      return (
        <SettingsSection scope="Agent configuration"
          title="Charter"
          description="The behaviour contract this agent works under."
        >
          <SettingsRow
            label="Charter"
            description="The markdown behaviour contract injected into this agent's turn context."
          >
            <CharterPicker agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

    case 'interaction':
      return (
        <SettingsSection scope="Agent configuration"
          title="Interaction"
          description="How long this agent holds its turn open for you before giving up and carrying on."
        >
          <WaitingSetting
            agent={agent}
            field="permission_timeout_seconds"
            label="Permission decision"
            fallback={PERMISSION_WAIT_FALLBACK_SECONDS}
            description="How long a run waits for you to allow or refuse an action under “Ask me”. Running out refuses it. Measured: the provider held a permission prompt open for at least 150s."
          />
          <WaitingSetting
            agent={agent}
            field="question_timeout_seconds"
            label="Answer to a question"
            fallback={QUESTION_WAIT_FALLBACK_SECONDS}
            description="How long a run waits for you to answer a question it asked. Longer than a permission decision, because you have to read it and choose. Measured: an ordinary tool call was held open for at least 240s."
          />
        </SettingsSection>
      )

    case 'context':
      return (
        <SettingsSection scope="Agent configuration"
          title="Context"
          description="How this agent's context window is managed across a session boundary."
        >
          <SettingsRow
            label="Checkpointing"
            description="When this agent's conversations are checkpointed, and how full the context gets first. The Hub writes the checkpoint from the conversation's own record; the agent is not asked to."
          >
            <CheckpointOverrideSetting agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

    case 'access':
      return <AccessSection agent={agent} />

    case 'workspace':
      return (
        <SettingsSection scope="Agent configuration"
          title="Workspace"
          description="Where this agent does its work on disk."
        >
          <WorkspaceLocation agent={agent.name} />
          <SettingsRow
            label="Provider sessions"
            description="The provider sessions recorded for this agent, and the directory each ran in. Diagnostic detail — AgentWeave addresses conversations by its own id, never by these."
          >
            <SessionList agent={agent.name} />
          </SettingsRow>
        </SettingsSection>
      )
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


/**
 * Where this agent works, and whether its isolated checkout exists yet.
 *
 * Two rows rather than one, because they answer different questions: *which directory* a turn
 * runs in, and *whether that directory is this agent's alone*. The second is the one that matters
 * when two agents edit the same repository — an isolated agent's work lands on its own branch and
 * has to be merged; a shared one edits the project checkout, where a second writer produces a lost
 * update rather than a conflict.
 *
 * Reading this provisions nothing. An agent that has never run still says where it will work,
 * because a panel that stayed empty until the first turn would read as one that failed to load.
 *
 * Isolation itself is not editable here. It is a real stored setting (`config.read_only`) that
 * nothing offers today, and giving it a control is a change of behaviour — flipping an agent with
 * uncommitted work in its worktree to the shared checkout would strand that work somewhere the
 * agent no longer looks. The Hub now holds that line on every door that can change it
 * (`isolation-does-not-change-under-held-work`): a change to where an agent works is refused, 409
 * `isolation_change_under_held_work`, while it has a running turn or an unfinished task. A control
 * here would still need its own change, not to be smuggled in behind a panel that was asked to
 * *show* the workspace.
 */
function WorkspaceLocation({ agent }: { agent: string }) {
  const { data, isLoading, error } = useAgentWorkspace(agent)

  if (isLoading) {
    return (
      <SettingsRow label="Working directory" description="Where a turn runs.">
        <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading…</span>
      </SettingsRow>
    )
  }
  if (!data) {
    return (
      <SettingsRow
        label="Working directory"
        description="Where a turn runs."
      >
        <span className="text-xs" style={{ color: 'var(--amber)' }} role="alert">
          {error instanceof ApiError ? error.message : 'The project workspace is unavailable.'}
        </span>
      </SettingsRow>
    )
  }

  return (
    <>
      <SettingsRow
        label="Working directory"
        description="The directory a turn runs in. Everything this agent reads or writes by relative path resolves from here."
      >
        <div>
          <code
            className="block truncate text-xs"
            data-testid="agent-working-dir"
            style={{
              background: 'var(--surface-2)',
              color: 'var(--text-2)',
              padding: '4px 8px',
              borderRadius: '4px',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {data.working_dir}
          </code>
          {/* A note, not an alert. This field once meant "your turns will be refused until you
            * fix this"; it now means "here is why you have no branch", and the turn runs either
            * way. Amber and `role="alert"` would announce a problem to a screen reader that the
            * operator does not have. The only reason it is said at all is that it is the one
            * thing telling them `git init` would change something. */}
          {data.unavailable_reason && (
            <p className="mt-2 text-[11px]" style={{ color: 'var(--text-3)' }}>
              {data.unavailable_reason}
            </p>
          )}
        </div>
      </SettingsRow>
      <SettingsRow
        label="Isolation"
        description="Whether this agent works in its own checkout. Its own means changes land on its own branch and are merged deliberately; the project checkout means a second writer overwrites rather than conflicts."
      >
        <div data-testid="agent-worktree">
          <span className="text-sm" style={{ color: 'var(--text)' }}>
            {data.isolated ? 'Its own git worktree' : 'Shares the project checkout'}
          </span>
          {data.isolated && (
            <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
              {data.branch}
              {' — '}
              {data.provisioned
                ? 'checked out and ready'
                : 'created the first time this agent runs'}
            </p>
          )}
        </div>
      </SettingsRow>
      <TaskCheckouts checkouts={data.task_checkouts ?? []} />
    </>
  )
}

/**
 * The checkouts of the tasks this agent is holding.
 *
 * The row above answers "where does a turn run", and for a task-bound turn that answer is not the
 * agent's own directory — an agent working three tasks works in three places, and this panel used
 * to name one of them. So this lists them, each with the branch and the task, because finding a
 * task's work should not require knowing how checkouts are named.
 *
 * Rendered only when there is something to say. An agent holding no tasks would otherwise get an
 * empty row that reads as a panel which failed to load, which is the same reason the working
 * directory is stated for an agent that has never run.
 */
function TaskCheckouts({ checkouts }: { checkouts: TaskCheckoutInfo[] }) {
  if (checkouts.length === 0) return null

  return (
    <SettingsRow
      label="Task checkouts"
      description="Each task this agent is working has its own checkout on its own branch. Work is merged when the task is approved, and the checkout is released then — the branch is kept."
    >
      <ul className="space-y-3" data-testid="agent-task-checkouts">
        {checkouts.map((checkout) => (
          <li key={checkout.task_id}>
            <div className="text-sm" style={{ color: 'var(--text)' }}>
              {checkout.title || checkout.task_id}
            </div>
            <code
              className="mt-1 block truncate text-[11px]"
              data-testid={`task-checkout-path-${checkout.task_id}`}
              style={{
                background: 'var(--surface-2)',
                color: 'var(--text-2)',
                padding: '3px 6px',
                borderRadius: '4px',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {checkout.path}
            </code>
            <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>
              {checkout.branch}
              {' — '}
              {/* Three states, not two. "Not provisioned" and "worked in the agent's own
                * checkout" look identical from the outside — no directory of this task's own —
                * but one becomes a checkout on the next turn and the other never will. An
                * operator told only "not created yet" would wait for something that is not
                * coming. */}
              {checkout.grandfathered
                ? "worked in this agent's own checkout, because this task started before per-task checkouts"
                : checkout.provisioned
                  ? 'checked out and ready'
                  : 'created the first time this task runs'}
            </p>
          </li>
        ))}
      </ul>
    </SettingsRow>
  )
}

/**
 * Provider sessions, with the directory each ran in.
 *
 * They sit under *Workspace* rather than with the conversation because what makes them useful is
 * the path: this is where the agent's work actually happened. `agent-conversation-workspace`
 * permits provider identity in a details or diagnostic surface and nowhere else, which this is —
 * no ordinary control addresses a conversation by one of these.
 */
function SessionList({ agent }: { agent: string }) {
  const { data, isLoading } = useAgentSessions(agent)
  const sessions = data?.sessions ?? []

  if (isLoading) {
    return <span className="text-xs" style={{ color: 'var(--text-3)' }}>Loading sessions…</span>
  }
  if (sessions.length === 0) {
    return <span className="text-xs" style={{ color: 'var(--text-3)' }}>No sessions yet.</span>
  }
  return (
    <div className="space-y-2" data-testid="agent-session-list">
      {sessions.map((session) => (
        <SessionRow key={session.id} session={session} />
      ))}
    </div>
  )
}

function SessionRow({ session }: { session: { id: string; type: string; path: string; last_active?: string } }) {
  const { copied, copy } = useCopy()

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg" style={{ background: 'var(--surface-3)' }}>
      <button
        onClick={() => copy(session.id)}
        className="flex-1 min-w-0 text-left"
        title="Click to copy session ID"
      >
        <code
          className="block truncate text-xs"
          style={{
            background: copied ? tint('var(--green)') : 'var(--surface-2)',
            color: copied ? 'var(--green)' : 'var(--text-3)',
            padding: '4px 8px',
            borderRadius: '4px',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {copied ? 'Copied!' : session.id}
        </code>
        {session.path && (
          <span className="mt-1 block truncate text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            {session.path}
          </span>
        )}
      </button>
      <span
        className="text-[11px] px-2 py-1 rounded-full shrink-0"
        style={{ background: 'var(--surface-2)', color: 'var(--text-3)', textTransform: 'capitalize' }}
      >
        {session.type}
      </span>
      {session.last_active && (
        <span className="text-[11px] shrink-0" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
          {formatDistanceToNow(hubDate(session.last_active), { addSuffix: true })}
        </span>
      )}
    </div>
  )
}

/* `NotYetPopulated` lived here and is gone: it held the Context and Access sections open for the
 * conversation-checkpoint change, and both are now filled. A placeholder kept past the thing it
 * was waiting for reads as a section that has nothing in it, rather than one that does. */
