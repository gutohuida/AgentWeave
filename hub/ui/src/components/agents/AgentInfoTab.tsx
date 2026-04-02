import { AgentSummary, useAgentSessions } from '@/api/agents'
import { useCopy } from '@/hooks/useCopy'
import { Icon } from '@/components/common/Icon'
import { formatDistanceToNow } from 'date-fns'

interface AgentInfoTabProps {
  agent: AgentSummary
}

const ROLE_CONFIG: Record<string, { bg: string; color: string }> = {
  principal: { bg: 'color-mix(in srgb, #3b82f6 15%, transparent)', color: '#3b82f6' },
  delegate: { bg: 'color-mix(in srgb, #22c55e 15%, transparent)', color: '#22c55e' },
  collaborator: { bg: 'color-mix(in srgb, var(--on-sv) 12%, transparent)', color: 'var(--on-sv)' },
}

const RUNNER_CONFIG: Record<string, { bg: string; color: string; label: string }> = {
  claude_proxy: { bg: 'color-mix(in srgb, #f59e0b 15%, transparent)', color: '#f59e0b', label: 'proxy' },
  manual: { bg: 'color-mix(in srgb, #6b7280 15%, transparent)', color: '#6b7280', label: 'manual' },
  native: { bg: 'color-mix(in srgb, #22c55e 15%, transparent)', color: '#22c55e', label: 'native' },
}

const STATUS_CONFIG: Record<string, { dotColor: string; label: string; pulse: boolean; labelColor: string }> = {
  running: { dotColor: '#22c55e', label: 'Running', pulse: true, labelColor: 'var(--primary)' },
  active: { dotColor: '#22c55e', label: 'Active', pulse: false, labelColor: 'var(--primary)' },
  idle: { dotColor: 'var(--border)', label: 'Idle', pulse: false, labelColor: 'var(--on-sv)' },
  waiting: { dotColor: '#f59e0b', label: 'Waiting', pulse: false, labelColor: 'var(--on-t-cont)' },
}

export function AgentInfoTab({ agent }: AgentInfoTabProps) {
  // Fetch sessions using React Query hook
  const { data: sessionsData, isLoading: isLoadingSessions } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []

  const statusCfg = STATUS_CONFIG[agent.status] ?? {
    dotColor: 'var(--border)', label: agent.status, pulse: false, labelColor: 'var(--on-sv)',
  }
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null

  return (
    <div
      className="flex-1 overflow-y-auto p-6 space-y-6"
      style={{ background: 'var(--surface-low)' }}
    >
      {/* Status Section */}
      <section className="m3-card-elevated p-4 rounded-xl">
        <h3 className="m3-title-small mb-4 flex items-center gap-2" style={{ color: 'var(--foreground)' }}>
          <Icon name="info" size={18} style={{ color: 'var(--primary)' }} />
          Status
        </h3>
        <div className="flex items-center gap-3 mb-3">
          <span className="relative flex h-3 w-3">
            {statusCfg.pulse && (
              <span
                className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
                style={{ background: statusCfg.dotColor }}
              />
            )}
            <span
              className="relative inline-flex rounded-full h-3 w-3"
              style={{ background: statusCfg.dotColor }}
            />
          </span>
          <span
            className="m3-body-large capitalize"
            style={{ color: statusCfg.labelColor, fontWeight: statusCfg.pulse ? 600 : 500 }}
          >
            {statusCfg.label}
          </span>
        </div>
        {agent.latest_status_msg && (
          <p className="m3-body-medium mb-3" style={{ color: 'var(--on-sv)' }}>
            {agent.latest_status_msg}
          </p>
        )}
        {agent.last_seen && (
          <p className="m3-body-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
            Last seen {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </p>
        )}
      </section>

      {/* Sessions Section */}
      <section className="m3-card-elevated p-4 rounded-xl">
        <h3 className="m3-title-small mb-4 flex items-center gap-2" style={{ color: 'var(--foreground)' }}>
          <Icon name="folder_open" size={18} style={{ color: 'var(--primary)' }} />
          Sessions
        </h3>
        {isLoadingSessions ? (
          <p className="m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="m3-body-medium" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
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
      <section className="m3-card-elevated p-4 rounded-xl">
        <h3 className="m3-title-small mb-4 flex items-center gap-2" style={{ color: 'var(--foreground)' }}>
          <Icon name="badge" size={18} style={{ color: 'var(--primary)' }} />
          Roles & Configuration
        </h3>

        {/* Collaboration Role */}
        {roleCfg && (
          <div className="mb-4">
            <p className="m3-label-small mb-2" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
              Collaboration Role
            </p>
            <span
              className="m3-label-small capitalize px-2 py-1 rounded-full inline-block"
              style={{ background: roleCfg.bg, color: roleCfg.color }}
            >
              {agent.role}
            </span>
          </div>
        )}

        {/* Dev Roles */}
        {(agent.dev_roles?.length || agent.dev_role) && (
          <div className="mb-4">
            <p className="m3-label-small mb-2" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
              Development Roles
            </p>
            <div className="flex flex-wrap gap-1.5">
              {agent.dev_roles?.map((role, idx) => (
                <span
                  key={role}
                  className="m3-label-small px-2 py-1 rounded-full"
                  style={{
                    background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                    color: '#8b5cf6',
                  }}
                >
                  {agent.dev_role_labels?.[idx] ?? role}
                </span>
              ))}
              {!agent.dev_roles?.length && agent.dev_role && (
                <span
                  className="m3-label-small px-2 py-1 rounded-full"
                  style={{
                    background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                    color: '#8b5cf6',
                  }}
                >
                  {agent.dev_role_label ?? agent.dev_role}
                </span>
              )}
            </div>
          </div>
        )}

        {/* YOLO & Runner */}
        <div className="flex flex-wrap gap-3">
          {/* YOLO Badge */}
          <div>
            <p className="m3-label-small mb-2" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
              YOLO Mode
            </p>
            {agent.yolo ? (
              <span
                className="m3-label-small px-2 py-1 rounded-full flex items-center gap-1"
                style={{
                  background: 'color-mix(in srgb, #f59e0b 15%, transparent)',
                  color: '#f59e0b',
                }}
              >
                <Icon name="bolt" size={14} />
                Enabled
              </span>
            ) : (
              <span
                className="m3-label-small px-2 py-1 rounded-full"
                style={{
                  background: 'var(--surface-high)',
                  color: 'var(--on-sv)',
                }}
              >
                Disabled
              </span>
            )}
          </div>

          {/* Runner Type */}
          {agent.runner && (
            <div>
              <p className="m3-label-small mb-2" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
                Runner
              </p>
              <span
                className="m3-label-small capitalize px-2 py-1 rounded-full"
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
      <section className="m3-card-elevated p-4 rounded-xl">
        <h3 className="m3-title-small mb-4 flex items-center gap-2" style={{ color: 'var(--foreground)' }}>
          <Icon name="bar_chart" size={18} style={{ color: 'var(--primary)' }} />
          Statistics
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface)' }}
          >
            <p className="m3-display-small" style={{ color: 'var(--primary)' }}>
              {agent.active_task_count}
            </p>
            <p className="m3-label-small mt-1" style={{ color: 'var(--on-sv)' }}>
              Active Tasks
            </p>
          </div>
          <div
            className="p-4 rounded-lg text-center"
            style={{ background: 'var(--surface)' }}
          >
            <p className="m3-display-small" style={{ color: 'var(--primary)' }}>
              {agent.message_count}
            </p>
            <p className="m3-label-small mt-1" style={{ color: 'var(--on-sv)' }}>
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
      style={{ background: 'var(--surface)' }}
    >
      <button
        onClick={() => copy(session.id)}
        className="flex-1 min-w-0 text-left group"
        title="Click to copy session ID"
      >
        <code
          className="m3-body-small block truncate"
          style={{
            background: copied ? 'color-mix(in srgb, #22c55e 15%, transparent)' : 'var(--surface-high)',
            color: copied ? '#22c55e' : 'var(--on-sv)',
            padding: '4px 8px',
            borderRadius: '4px',
            fontFamily: 'monospace',
          }}
        >
          {copied ? 'Copied!' : session.id}
        </code>
      </button>
      <span
        className="m3-label-small px-2 py-1 rounded-full shrink-0"
        style={{
          background: 'var(--surface-high)',
          color: 'var(--on-sv)',
          textTransform: 'capitalize',
        }}
      >
        {session.type}
      </span>
      {session.last_active && (
        <span className="m3-label-small shrink-0" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          {formatDistanceToNow(new Date(session.last_active), { addSuffix: true })}
        </span>
      )}
    </div>
  )
}
