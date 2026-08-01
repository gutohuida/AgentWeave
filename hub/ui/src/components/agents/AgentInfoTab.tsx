import { AgentSummary, useAgentSessions } from '@/api/agents'
import { useCopy } from '@/hooks/useCopy'
import { Icon } from '@/components/common/Icon'
import { formatDistanceToNow } from 'date-fns'
import { getStatusConfig, StatusDot, DevRoleTagList } from '@/lib/agentStatus'

interface AgentInfoTabProps {
  agent: AgentSummary
}

const ROLE_CONFIG: Record<string, { bg: string; color: string }> = {
  principal: { bg: 'rgba(59,130,246,0.1)', color: 'var(--blue)' },
  delegate: { bg: 'rgba(34,197,94,0.1)', color: 'var(--green)' },
  collaborator: { bg: 'rgba(161,161,170,0.1)', color: 'var(--text-3)' },
}

const RUNNER_CONFIG: Record<string, { bg: string; color: string; label: string }> = {
  claude_proxy: { bg: 'rgba(245,158,11,0.1)', color: 'var(--amber)', label: 'proxy' },
  manual: { bg: 'rgba(161,161,170,0.1)', color: 'var(--text-3)', label: 'manual' },
  native: { bg: 'rgba(34,197,94,0.1)', color: 'var(--green)', label: 'native' },
  copilot: { bg: 'rgba(36,160,242,0.1)', color: '#24a0f2', label: 'copilot' },
}

export function AgentInfoTab({ agent }: AgentInfoTabProps) {
  const { data: sessionsData, isLoading: isLoadingSessions } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  const statusCfg = getStatusConfig(agent.status)
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null

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

      {/* Roles & Configuration Section */}
      <section style={cardStyle}>
        <h3 className="mb-4 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
          <Icon name="badge" size={18} style={{ color: 'var(--blue)' }} />
          Roles & Configuration
        </h3>

        {/* Collaboration Role */}
        {roleCfg && (
          <div className="mb-4">
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              Collaboration Role
            </p>
            <span
              className="text-[11px] font-medium capitalize px-2 py-1 rounded-full inline-block"
              style={{ background: roleCfg.bg, color: roleCfg.color }}
            >
              {agent.role}
            </span>
          </div>
        )}

        {/* Dev Roles */}
        {(agent.dev_roles?.length || agent.dev_role) && (
          <div className="mb-4">
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              Development Roles
            </p>
            <div className="flex flex-wrap gap-1.5">
              <DevRoleTagList agent={agent} size="md" />
            </div>
          </div>
        )}

        {/* YOLO & Runner */}
        <div className="flex flex-wrap gap-3">
          {/* YOLO Badge */}
          <div>
            <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              YOLO Mode
            </p>
            {agent.yolo ? (
              <span
                className="text-[11px] font-medium px-2 py-1 rounded-full flex items-center gap-1"
                style={{
                  background: 'rgba(245,158,11,0.1)',
                  color: 'var(--amber)',
                }}
              >
                <Icon name="bolt" size={14} />
                Enabled
              </span>
            ) : (
              <span
                className="text-[11px] font-medium px-2 py-1 rounded-full"
                style={{
                  background: 'var(--surface-3)',
                  color: 'var(--text-3)',
                }}
              >
                Disabled
              </span>
            )}
          </div>

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
            background: copied ? 'rgba(34,197,94,0.1)' : 'var(--surface-2)',
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
