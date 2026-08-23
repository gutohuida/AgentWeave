import { formatDistanceToNow } from 'date-fns'
import { AgentSummary, useAgents, useAgentSessions, useArchiveAgent } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/api/client'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { useAgentWorkspace } from '@/api/workspace'
import { useCopy } from '@/hooks/useCopy'
import { tint } from '@/lib/colorTint'
import {
  CharterPicker,
  CheckpointGrantsSetting,
  EvidenceGrantSetting,
  CheckpointOverrideSetting,
  DescriptionSetting,
  PermissionDefaultSetting,
  RunnerPicker,
  WaitingSetting,
} from './AgentSettingsControls'
import type { AgentSettingsSection } from '@/lib/navigation'
import { hubDate } from '@/lib/hubTime'

interface AgentSettingsPageProps {
  agent: string
  section: AgentSettingsSection
}

/**
 * An agent's configuration, as a destination rather than a dialog.
 *
 * The section list and the back control live in the rail (see `Sidebar`), following the shape the
 * project's own configuration already uses — so this component renders one section's contents and
 * nothing else.
 *
 * *Context* and *Access* are defined here ahead of the change that fills them
 * (`2026-08-07-conversation-handoff-rework` section 8). They render what exists at the time, which
 * is today nothing — stated plainly, because a section that renders blank is indistinguishable
 * from one that failed to load.
 */
export function AgentSettingsPage({ agent, section }: AgentSettingsPageProps) {
  // `all`, not the default open roster: an archived agent must still resolve here, because this
  // is the only surface that can unarchive it.
  const { data: roster = [], isLoading } = useAgents('all')
  const summary = roster.find((candidate) => candidate.name === agent) ?? null

  if (isLoading) {
    return (
      <div className="workspace-content space-y-3" aria-label="Loading agent settings">
        <div className="skeleton h-6 w-32" />
        <div className="skeleton h-4 w-80 max-w-full" />
        {[0, 1, 2].map((row) => <div key={row} className="skeleton h-20 w-full" />)}
      </div>
    )
  }
  if (!summary) {
    return <Shell>This agent is no longer in the roster.</Shell>
  }

  return (
    <div className="min-w-0 h-full overflow-auto" data-testid={`agent-settings-${section}`}>
      <SectionContent agent={summary} section={section} />
    </div>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-6 py-6 text-xs" style={{ color: 'var(--text-3)' }} data-testid="agent-settings-empty">
      {children}
    </div>
  )
}

function SectionContent({ agent, section }: { agent: AgentSummary; section: AgentSettingsSection }) {
  switch (section) {
    case 'identity':
      return (
        <SettingsSection scope="Agent configuration" title="Identity" description="What this agent is called, and whether it is in use.">
          <SettingsRow
            label="Name"
            description="How this agent is addressed — by you, and by its peers when they send it a message."
          >
            <span className="text-sm" style={{ color: 'var(--text)' }}>{agent.name}</span>
          </SettingsRow>
          <SettingsRow
            label="Description"
            description="What this agent is for, for you. Nothing reads it into a turn — the charter is where behaviour is stated."
          >
            <DescriptionSetting agent={agent} />
          </SettingsRow>
          <SettingsRow
            label={agent.lifecycle === 'archived' ? 'Archived' : 'Archive'}
            description={
              agent.lifecycle === 'archived'
                ? 'This agent is no longer offered anywhere an agent is chosen. Its conversations, runs and messages are unchanged, and you can bring it back at any time.'
                : 'Take this agent out of the rail, task assignment and peer recipients without losing anything it has done. There is no way to delete an agent, by design — its name is the attribution on everything it produced.'
            }
          >
            <ArchiveControl agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

    case 'execution':
      return (
        <SettingsSection scope="Agent configuration"
          title="Execution"
          description="What this agent runs as when you give it a turn."
        >
          <SettingsRow
            label="Runner"
            description="The execution capability this agent is bound to — its CLI, model and flags."
          >
            <RunnerPicker agent={agent} />
          </SettingsRow>
          <SettingsRow
            label="Default permissions"
            description="What this agent may do when a conversation has not chosen a posture. The composer's Permissions pill overrides it for one conversation; this is what everything else starts from."
          >
            <PermissionDefaultSetting agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

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
            fallback={120}
            description="How long a run waits for you to allow or refuse an action under “Ask me”. Running out refuses it. Measured: the provider held a permission prompt open for at least 150s."
          />
          <WaitingSetting
            agent={agent}
            field="question_timeout_seconds"
            label="Answer to a question"
            fallback={240}
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
      return (
        <SettingsSection scope="Agent configuration"
          title="Access"
          description="What this agent may read of other agents' work, and what it may decide about it."
        >
          <SettingsRow
            label="Grants"
            description="Both closed by default. Reading a summary of a peer's work and reading the raw output behind it are different permissions, so they are granted separately."
          >
            <CheckpointGrantsSetting agent={agent} />
          </SettingsRow>
          <SettingsRow
            label="Evidence"
            description="Separate from the grants above, because this is not a widening of what can be read — it is authority over whether work is allowed to merge."
          >
            <EvidenceGrantSetting agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

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

/**
 * Archive and unarchive.
 *
 * The refusal is the interesting case. Archiving is refused — with the reason — while a run is in
 * progress or messages are undelivered, rather than stopping the run or dropping the messages to
 * get its way. So the error is rendered as the operator's next instruction, not as a failure.
 */
function ArchiveControl({ agent }: { agent: AgentSummary }) {
  const archive = useArchiveAgent()
  const archived = agent.lifecycle === 'archived'
  const queueRefusal = archive.error instanceof ApiError ? parseQueueArchiveRefusal(archive.error) : null
  const refusal = archive.error instanceof ApiError
    ? queueRefusal?.message ?? archive.error.message
    : archive.error ? 'Could not save.' : null

  return (
    <div>
      <Button
        variant={archived ? 'outline' : 'destructive'}
        size="sm"
        data-testid="agent-archive-toggle"
        disabled={archive.isPending}
        onClick={() => archive.mutate({ agent: agent.name, archived: !archived })}
      >
        {archived ? 'Unarchive agent' : 'Archive agent'}
      </Button>
      {refusal && (
        <div role="alert" className="mt-2 space-y-2 text-[11px]" style={{ color: 'var(--amber)' }}>
          <p>{refusal}</p>
          {queueRefusal && (
            <Button
              variant="destructive"
              size="sm"
              disabled={archive.isPending}
              onClick={() => archive.mutate({
                agent: agent.name,
                archived: true,
                discardQueueEntryIds: queueRefusal.ids,
              })}
            >
              Discard {queueRefusal.ids.length} queued message{queueRefusal.ids.length === 1 ? '' : 's'} and archive — cannot be undone
            </Button>
          )}
        </div>
      )}
    </div>
  )
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
 * agent no longer looks. That belongs in its own change, with a decision about what happens to the
 * existing worktree, not smuggled in behind a panel that was asked to *show* the workspace.
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
    </>
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
