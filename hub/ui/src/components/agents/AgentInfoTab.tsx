import { AgentSummary, useAgentSessions, useRegisterSession, useSetPilotMode } from '@/api/agents'
import { useCopy } from '@/hooks/useCopy'
import { Icon } from '@/components/common/Icon'
import { formatDistanceToNow } from 'date-fns'
import { useState } from 'react'

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
}

const STATUS_CONFIG: Record<string, { dotColor: string; label: string; pulse: boolean; labelColor: string }> = {
  running: { dotColor: 'var(--green)', label: 'Running', pulse: true, labelColor: 'var(--green)' },
  active: { dotColor: 'var(--green)', label: 'Active', pulse: false, labelColor: 'var(--green)' },
  idle: { dotColor: 'var(--text-3)', label: 'Idle', pulse: false, labelColor: 'var(--text-3)' },
  waiting: { dotColor: 'var(--amber)', label: 'Waiting', pulse: false, labelColor: 'var(--amber)' },
}

export function AgentInfoTab({ agent }: AgentInfoTabProps) {
  const { data: sessionsData, isLoading: isLoadingSessions } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions || []
  const registerSession = useRegisterSession()
  const setPilotMode = useSetPilotMode()
  const [sessionIdInput, setSessionIdInput] = useState('')

  const statusCfg = STATUS_CONFIG[agent.status] ?? {
    dotColor: 'var(--text-3)', label: agent.status, pulse: false, labelColor: 'var(--text-3)',
  }
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null

  const handleRegisterSession = (e: React.FormEvent) => {
    e.preventDefault()
    if (sessionIdInput.trim()) {
      registerSession.mutate({ agent: agent.name, sessionId: sessionIdInput.trim() })
      setSessionIdInput('')
    }
  }

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

      {/* Pilot Mode Section */}
      {agent.pilot ? (
        <section style={cardStyle}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
              <Icon name="flight" size={18} style={{ color: '#ec4899' }} />
              Pilot Mode
            </h3>
            <button
              onClick={() => setPilotMode.mutate({ agent: agent.name, enabled: false })}
              disabled={setPilotMode.isPending}
              className="text-[11px] font-medium px-3 py-1 rounded transition-opacity"
              style={{
                background: 'var(--surface-3)',
                color: 'var(--text-3)',
                border: '1px solid var(--border)',
                opacity: setPilotMode.isPending ? 0.5 : 1,
              }}
              title="Disable pilot mode to allow auto-execution"
            >
              {setPilotMode.isPending ? 'Disabling...' : 'Disable'}
            </button>
          </div>

          {/* Registered Session ID */}
          {agent.registered_session_id && (
            <div className="mb-4">
              <p className="text-[11px] mb-2" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                Active Session
              </p>
              <RegisteredSessionRow sessionId={agent.registered_session_id} />
            </div>
          )}

          {/* Register Session Form */}
          <form onSubmit={handleRegisterSession} className="space-y-2">
            <p className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
              Register New Session
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={sessionIdInput}
                onChange={(e) => setSessionIdInput(e.target.value)}
                placeholder="Enter session ID..."
                className="flex-1 px-3 py-2 rounded text-xs"
                style={{
                  background: 'var(--surface-3)',
                  border: '1px solid var(--border)',
                  color: 'var(--text)',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                disabled={!sessionIdInput.trim() || registerSession.isPending}
                className="px-4 py-2 rounded text-xs font-medium transition-opacity"
                style={{
                  background: 'var(--blue)',
                  color: '#fff',
                  opacity: !sessionIdInput.trim() || registerSession.isPending ? 0.5 : 1,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {registerSession.isPending ? 'Registering...' : 'Register'}
              </button>
            </div>
            {registerSession.isError && (
              <p className="text-xs" style={{ color: 'var(--red)' }}>
                Failed to register session
              </p>
            )}
          </form>
        </section>
      ) : (
        <section style={cardStyle}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="mb-1 flex items-center gap-2 text-[13px] font-medium" style={{ color: 'var(--text)' }}>
                <Icon name="flight" size={18} style={{ color: 'var(--text-3)' }} />
                Pilot Mode
              </h3>
              <p className="text-xs" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                Enable manual control and disable auto-execution
              </p>
            </div>
            <button
              onClick={() => setPilotMode.mutate({ agent: agent.name, enabled: true })}
              disabled={setPilotMode.isPending}
              className="text-xs font-medium px-4 py-2 rounded transition-opacity"
              style={{
                background: '#ec4899',
                color: '#fff',
                opacity: setPilotMode.isPending ? 0.5 : 1,
                border: 'none',
                cursor: 'pointer',
              }}
              title="Enable pilot mode for manual control"
            >
              {setPilotMode.isPending ? 'Enabling...' : 'Enable'}
            </button>
          </div>
        </section>
      )}

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
              {agent.dev_roles?.map((role, idx) => (
                <span
                  key={role}
                  className="text-[11px] px-2 py-1 rounded-full"
                  style={{
                    background: 'rgba(168,85,247,0.1)',
                    color: 'var(--purple)',
                  }}
                >
                  {agent.dev_role_labels?.[idx] ?? role}
                </span>
              ))}
              {!agent.dev_roles?.length && agent.dev_role && (
                <span
                  className="text-[11px] px-2 py-1 rounded-full"
                  style={{
                    background: 'rgba(168,85,247,0.1)',
                    color: 'var(--purple)',
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

function RegisteredSessionRow({ sessionId }: { sessionId: string }) {
  const { copied, copy } = useCopy()

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-lg"
      style={{ background: 'var(--surface-3)' }}
    >
      <button
        onClick={() => copy(sessionId)}
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
          {copied ? 'Copied!' : sessionId}
        </code>
      </button>
      <Icon
        name={copied ? 'check' : 'content_copy'}
        size={16}
        style={{ color: copied ? 'var(--green)' : 'var(--text-3)' }}
      />
    </div>
  )
}
