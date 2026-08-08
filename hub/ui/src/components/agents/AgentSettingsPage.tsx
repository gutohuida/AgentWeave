import { AgentSummary, useAgents } from '@/api/agents'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
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
  const { data: roster = [], isLoading } = useAgents()
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
        <SettingsSection title="Identity" description="What this agent is called.">
          <SettingsRow
            label="Name"
            description="How this agent is addressed — by you, and by its peers when they send it a message."
          >
            <span className="text-sm" style={{ color: 'var(--text)' }}>{agent.name}</span>
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
          <NotYetPopulated>
            This agent's worktree and working directory are not yet editable here.
          </NotYetPopulated>
        </SettingsSection>
      )
  }
}

function NotYetPopulated({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-1 py-3 text-xs" style={{ color: 'var(--text-3)' }}>
      {children}
    </p>
  )
}
