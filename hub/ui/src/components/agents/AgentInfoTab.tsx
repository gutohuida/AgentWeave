import { AgentSummary, useAgentSessions } from '@/api/agents'
import { SettingsRow, SettingsSection } from '@/components/environment/SettingsSection'
import { CharterPicker, RunnerPicker, WaitingSetting } from './AgentSettingsControls'
import { useCopy } from '@/hooks/useCopy'
import { Icon } from '@/components/common/Icon'
import { formatDistanceToNow } from 'date-fns'
import { getStatusConfig, StatusDot } from '@/lib/agentStatus'
import { tint } from '@/lib/colorTint'

interface AgentInfoTabProps {
  agent: AgentSummary
}

const RUNNER_CONFIG: Record<string, { bg: string; color: string; label: string }> = {
  claude_proxy: { bg: tint('var(--amber)'), color: 'var(--amber)', label: 'proxy' },
  manual: { bg: tint('var(--text-3)'), color: 'var(--text-3)', label: 'manual' },
  native: { bg: tint('var(--green)'), color: 'var(--green)', label: 'native' },
  copilot: { bg: tint('var(--blue)'), color: 'var(--blue)', label: 'copilot' },
}

export function AgentInfoTab({ agent }: AgentInfoTabProps) {
  const { data: sessionsData, isLoading: isLoadingSessions } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  const statusCfg = getStatusConfig(agent.status)

  const cardStyle: React.CSSProperties = {
    background: 'var(--surface-2)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: 16,
  }

  return (
    <div
      className="flex-1 overflow-y-auto p-6 space-y-6"
      style={{ background: 'var(--surface)' }}
    >
      {/* Status Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="info" size={18} style={{ color: 'var(--blue)' }} />
          Status
        </h3>
        <div className="flex items-center gap-3 mb-3">
          <StatusDot status={agent.status} size="lg" />
          <span
            className="text-sm capitalize"
            style={{ color: statusCfg.labelColor, fontWeight: statusCfg.pulse ? 600 : 500 }}
          >
            {statusCfg.label}
          </span>
        </div>
        {agent.latest_status_msg && (
          <p className="text-sm mb-3" style={{ color: 'var(--text-3)' }}>
            {agent.latest_status_msg}
          </p>
        )}
        {agent.last_seen && (
          <p className="text-xs" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            Last seen {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </p>
        )}
      </section>

      {/* Sessions Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="folder_open" size={18} style={{ color: 'var(--blue)' }} />
          Sessions
        </h3>
        {isLoadingSessions ? (
          <p className="text-sm" style={{ color: 'var(--text-3)' }}>Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="text-sm" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            No sessions yet
          </p>
        ) : (
          <div className="space-y-2">
            {sessions.map((session) => (
              <SessionRow key={session.id} session={session} />
            ))}
          </div>
        )}
      </section>

      {/* Configuration Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="badge" size={18} style={{ color: 'var(--blue)' }} />
          Configuration
        </h3>

        <div className="flex flex-wrap gap-3">
          {/* Runner Type */}
          {agent.runner && (
            <div>
              <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                Runner
              </p>
              <span
                className="text-[11px] font-medium capitalize px-2 py-1 rounded-full"
                style={{
                  background: RUNNER_CONFIG[agent.runner]?.bg || RUNNER_CONFIG.manual.bg,
                  color: RUNNER_CONFIG[agent.runner]?.color || RUNNER_CONFIG.manual.color,
                }}
              >
                {RUNNER_CONFIG[agent.runner]?.label || agent.runner}
              </span>
            </div>
          )}
        </div>

      </section>

      {/* The editable settings, on the same components the project settings panel uses, so the
          two read as one system rather than two panels that happen to both have controls. */}
      <SettingsSection
        title="Bindings"
        description="What this agent runs as, and the behaviour contract it works under."
      >
        <SettingsRow
          label="Runner"
          description="The execution capability this agent is bound to — its CLI, model and flags."
        >
          <RunnerPicker agent={agent} />
        </SettingsRow>
        <SettingsRow
          label="Charter"
          description="The markdown behaviour contract injected into this agent's turn context."
        >
          <CharterPicker agent={agent} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        title="Waiting for you"
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

      {/* Stats Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="bar_chart" size={18} style={{ color: 'var(--blue)' }} />
          Statistics
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface-3)' }}
          >
            <p className="text-4xl font-normal" style={{ color: 'var(--blue)' }}>
              {agent.active_task_count}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
              Active Tasks
            </p>
          </div>
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface-3)' }}
          >
            <p className="text-4xl font-normal" style={{ color: 'var(--blue)' }}>
              {agent.message_count}
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-3)' }}>
              Messages
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

function SessionRow({ session }: { session: { id: string; type: string; path: string; last_active?: string } }) {
  const { copied, copy } = useCopy()

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-lg"
      style={{ background: 'var(--surface-3)' }}
    >
      <button
        onClick={() => copy(session.id)}
        className="flex-1 min-w-0 text-left group"
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
      </button>
      <span
        className="text-[11px] px-2 py-1 rounded-full shrink-0"
        style={{
          background: 'var(--surface-2)',
          color: 'var(--text-3)',
          textTransform: 'capitalize',
        }}
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
