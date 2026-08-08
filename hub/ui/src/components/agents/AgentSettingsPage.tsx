import { formatDistanceToNow } from 'date-fns'
import { AgentSummary, useAgents, useAgentSessions, useArchiveAgent } from '@/api/agents'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/api/client'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { useCopy } from '@/hooks/useCopy'
import { tint } from '@/lib/colorTint'
import { CharterPicker, RunnerPicker, WaitingSetting } from './AgentSettingsControls'
import type { AgentSettingsSection } from '@/lib/navigation'

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
    return <Shell>Loading…</Shell>
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
        <SettingsSection title="Identity" description="What this agent is called, and whether it is in use.">
          <SettingsRow
            label="Name"
            description="How this agent is addressed — by you, and by its peers when they send it a message."
          >
            <span className="text-sm" style={{ color: 'var(--text)' }}>{agent.name}</span>
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
        <SettingsSection
          title="Execution"
          description="What this agent runs as when you give it a turn."
        >
          <SettingsRow
            label="Runner"
            description="The execution capability this agent is bound to — its CLI, model and flags."
          >
            <RunnerPicker agent={agent} />
          </SettingsRow>
        </SettingsSection>
      )

    case 'charter':
      return (
        <SettingsSection
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
        <SettingsSection
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
        <SettingsSection
          title="Context"
          description="How this agent's context window is managed across a session boundary."
        >
          <NotYetPopulated>
            Automatic checkpoints and their threshold are defined by the conversation-checkpoint
            change and will appear here. Nothing is configurable yet.
          </NotYetPopulated>
        </SettingsSection>
      )

    case 'access':
      return (
        <SettingsSection
          title="Access"
          description="What this agent may read of other agents' work."
        >
          <NotYetPopulated>
            Checkpoint-summary and transcript grants are defined by the conversation-checkpoint
            change and will appear here. Both are closed until then.
          </NotYetPopulated>
        </SettingsSection>
      )

    case 'workspace':
      return (
        <SettingsSection
          title="Workspace"
          description="Where this agent does its work on disk."
        >
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
  const refusal =
    archive.error instanceof ApiError ? archive.error.message : archive.error ? 'Could not save.' : null

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
        <p role="alert" className="mt-2 text-[11px]" style={{ color: 'var(--amber)' }}>
          {refusal}
        </p>
      )}
    </div>
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
          {formatDistanceToNow(new Date(session.last_active), { addSuffix: true })}
        </span>
      )}
    </div>
  )
}

function NotYetPopulated({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-1 py-3 text-xs" style={{ color: 'var(--text-3)' }}>
      {children}
    </p>
  )
}
