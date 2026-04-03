import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { useAgents, useAgentSessions, AgentSummary } from '@/api/agents'
import { requestCompact, requestNewSession } from '@/api/context'
import { Icon } from '@/components/common/Icon'

// ─── Context bar ────────────────────────────────────────────────────────────

function contextBarColor(percent: number, warning: boolean): string {
  if (warning || percent >= 70) return '#ef4444'
  if (percent >= 40) return '#f59e0b'
  return '#22c55e'
}

interface ContextBarProps {
  agent: AgentSummary
}

function ContextBar({ agent }: ContextBarProps) {
  const ctx = agent.context_usage
  if (!ctx || ctx.percent == null) {
    return (
      <div className="mt-2">
        <div
          className="h-1.5 rounded-full"
          style={{ background: 'var(--outline-variant)' }}
        />
        <p className="mt-1 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.5 }}>
          No context data
        </p>
      </div>
    )
  }

  const pct = Math.min(100, Math.max(0, ctx.percent))
  const color = contextBarColor(pct, !!ctx.warning)

  return (
    <div className="mt-2">
      <div className="flex items-center justify-between mb-0.5">
        <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
          {ctx.model ?? 'context'}
        </span>
        <span
          className="m3-label-small font-semibold"
          style={{ color }}
        >
          {pct}%
        </span>
      </div>
      <div
        className="h-1.5 w-full rounded-full overflow-hidden"
        style={{ background: 'var(--outline-variant)' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      {ctx.threshold_warning != null && (
        <p className="mt-0.5 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.5 }}>
          threshold {ctx.threshold_warning}%
          {ctx.warning && (
            <span style={{ color: '#f59e0b', marginLeft: 6 }}>⚠ warning</span>
          )}
          {ctx.critical && (
            <span style={{ color: '#ef4444', marginLeft: 6 }}>✕ critical</span>
          )}
        </p>
      )}
    </div>
  )
}

// ─── Agent mission card ───────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { dotColor: string; label: string; pulse: boolean }> = {
  running: { dotColor: '#22c55e', label: 'Running', pulse: true },
  active:  { dotColor: '#22c55e', label: 'Active',  pulse: false },
  idle:    { dotColor: 'var(--border)', label: 'Idle', pulse: false },
  waiting: { dotColor: '#f59e0b', label: 'Waiting', pulse: false },
}

const ROLE_CONFIG: Record<string, { bg: string; color: string }> = {
  principal:    { bg: 'color-mix(in srgb, #3b82f6 15%, transparent)', color: '#3b82f6' },
  delegate:     { bg: 'color-mix(in srgb, #22c55e 15%, transparent)', color: '#22c55e' },
  collaborator: { bg: 'color-mix(in srgb, var(--on-sv) 12%, transparent)', color: 'var(--on-sv)' },
}

interface MissionCardProps {
  agent: AgentSummary
}

function MissionCard({ agent }: MissionCardProps) {
  const [compacting, setCompacting] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const { data: sessionsData } = useAgentSessions(agent.name)
  const sessions = sessionsData?.sessions ?? []
  const activeSession = sessions[0] ?? null

  const cfg = STATUS_CONFIG[agent.status] ?? {
    dotColor: 'var(--border)', label: agent.status, pulse: false,
  }
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null
  const hasWarning = !!agent.context_usage?.warning || !!agent.context_usage?.critical

  async function handleCompact() {
    setCompacting(true)
    try {
      await requestCompact(agent.name)
      setActionMsg('Compact request sent')
    } catch {
      setActionMsg('Failed to send')
    } finally {
      setCompacting(false)
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  async function handleResetConfirm() {
    setResetting(true)
    setConfirmReset(false)
    try {
      await requestNewSession(agent.name)
      setActionMsg('Context reset requested')
    } catch {
      setActionMsg('Failed to send')
    } finally {
      setResetting(false)
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-0"
      style={{
        background: 'var(--surface-highest)',
        border: `1px solid ${hasWarning ? 'color-mix(in srgb, #f59e0b 40%, transparent)' : 'var(--outline-variant)'}`,
      }}
    >
      {/* Header: name + status */}
      <div className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          {cfg.pulse && (
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
              style={{ background: cfg.dotColor }}
            />
          )}
          <span
            className="relative inline-flex rounded-full h-2.5 w-2.5"
            style={{ background: cfg.dotColor }}
          />
        </span>
        <span
          className="m3-title-small flex-1 font-semibold"
          style={{ color: 'var(--foreground)' }}
        >
          {agent.name}
        </span>
        <span
          className="m3-label-small capitalize"
          style={{ color: cfg.dotColor }}
        >
          {cfg.label}
        </span>
      </div>

      {/* Role badges */}
      {(roleCfg || agent.dev_roles?.length || agent.dev_role) && (
        <div className="mt-1.5 flex gap-1.5 flex-wrap">
          {roleCfg && (
            <span
              className="m3-label-small capitalize px-1.5 py-0.5 rounded-full"
              style={{ background: roleCfg.bg, color: roleCfg.color, fontSize: '0.65rem' }}
            >
              {agent.role}
            </span>
          )}
          {agent.dev_roles?.map((role, idx) => (
            <span
              key={role}
              className="m3-label-small px-1.5 py-0.5 rounded-full"
              style={{
                background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                color: '#8b5cf6',
                fontSize: '0.65rem',
              }}
            >
              {agent.dev_role_labels?.[idx] ?? role}
            </span>
          ))}
          {!agent.dev_roles?.length && agent.dev_role && (
            <span
              className="m3-label-small px-1.5 py-0.5 rounded-full"
              style={{
                background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                color: '#8b5cf6',
                fontSize: '0.65rem',
              }}
            >
              {agent.dev_role_label ?? agent.dev_role}
            </span>
          )}
        </div>
      )}

      {/* Stats row */}
      <div className="mt-2 flex gap-3 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
        <span>{agent.active_task_count} tasks</span>
        <span>{agent.message_count} msgs</span>
        {agent.last_seen && (
          <span className="ml-auto">
            {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </span>
        )}
      </div>

      {/* Context bar */}
      <ContextBar agent={agent} />

      {/* Active session info */}
      <div
        className="mt-3 rounded-lg px-3 py-2"
        style={{ background: 'color-mix(in srgb, var(--on-sv) 5%, transparent)', border: '1px solid var(--outline-variant)' }}
      >
        <div className="flex items-center gap-1 mb-1">
          <Icon name="history" size={12} style={{ color: 'var(--on-sv)', opacity: 0.5 } as React.CSSProperties} />
          <span className="m3-label-small font-medium" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
            Active Session
          </span>
          {sessions.length > 0 && (
            <span
              className="ml-auto m3-label-small px-1.5 py-0.5 rounded-full"
              style={{ background: 'color-mix(in srgb, var(--primary) 12%, transparent)', color: 'var(--primary)', fontSize: '0.6rem' }}
            >
              {sessions.length} total
            </span>
          )}
        </div>
        {activeSession ? (
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
              <span title={activeSession.id} style={{ fontFamily: 'monospace', fontSize: '0.65rem' }}>
                {activeSession.id.slice(0, 8)}…
              </span>
              <span className="ml-auto">
                {activeSession.last_active
                  ? formatDistanceToNow(new Date(activeSession.last_active), { addSuffix: true })
                  : '—'}
              </span>
            </div>
            {activeSession.started_at && (
              <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.45, fontSize: '0.6rem' }}>
                started {formatDistanceToNow(new Date(activeSession.started_at), { addSuffix: true })}
              </span>
            )}
          </div>
        ) : (
          <p className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.4 }}>No session data yet</p>
        )}
      </div>

      {/* Action buttons */}
      <div className="mt-2 flex gap-2">
        <button
          onClick={handleCompact}
          disabled={compacting}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg m3-label-medium transition-colors disabled:opacity-50"
          style={{
            background: 'color-mix(in srgb, var(--primary) 12%, transparent)',
            color: 'var(--primary)',
            border: '1px solid color-mix(in srgb, var(--primary) 25%, transparent)',
          }}
          title="Send compact request to agent"
        >
          <Icon name="compress" size={14} />
          <span>Compact</span>
        </button>
        {confirmReset ? (
          <div className="flex-1 flex gap-1">
            <button
              onClick={() => setConfirmReset(false)}
              className="flex-1 py-1.5 rounded-lg m3-label-medium transition-colors"
              style={{ background: 'color-mix(in srgb, var(--on-sv) 8%, transparent)', color: 'var(--on-sv)', border: '1px solid var(--outline-variant)' }}
            >
              Cancel
            </button>
            <button
              onClick={handleResetConfirm}
              disabled={resetting}
              className="flex-1 py-1.5 rounded-lg m3-label-medium transition-colors disabled:opacity-50"
              style={{ background: 'color-mix(in srgb, #f59e0b 15%, transparent)', color: '#f59e0b', border: '1px solid color-mix(in srgb, #f59e0b 35%, transparent)' }}
            >
              Confirm
            </button>
          </div>
        ) : (
          <button
            onClick={() => setConfirmReset(true)}
            disabled={resetting}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg m3-label-medium transition-colors disabled:opacity-50"
            style={{
              background: 'color-mix(in srgb, var(--on-sv) 8%, transparent)',
              color: 'var(--on-sv)',
              border: '1px solid var(--outline-variant)',
            }}
            title="Reset agent context — starts a new session. Old sessions remain accessible from the agent screen."
          >
            <Icon name="refresh" size={14} />
            <span>Reset Context</span>
          </button>
        )}
      </div>

      {/* Confirm hint */}
      {confirmReset && (
        <p className="mt-1 m3-label-small text-center" style={{ color: '#f59e0b', fontSize: '0.6rem' }}>
          Starts a fresh context. Old sessions stay accessible from the agent screen.
        </p>
      )}

      {/* Action feedback */}
      {actionMsg && (
        <p className="mt-1.5 m3-label-small text-center" style={{ color: 'var(--primary)' }}>
          {actionMsg}
        </p>
      )}
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export function MissionControlPage() {
  const { data: agents = [], isLoading } = useAgents()

  const warningCount = agents.filter(
    (a) => a.context_usage?.warning || a.context_usage?.critical
  ).length

  return (
    <div className="h-full overflow-auto p-6">
      {/* Page header */}
      <div className="flex items-center gap-3 mb-6">
        <div>
          <h1 className="m3-title-large" style={{ color: 'var(--foreground)' }}>
            Mission Control
          </h1>
          <p className="m3-body-small mt-0.5" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
            Context usage and agent health at a glance
          </p>
        </div>
        {warningCount > 0 && (
          <span
            className="ml-auto px-3 py-1 rounded-full m3-label-medium flex items-center gap-1.5"
            style={{ background: 'var(--error-cont)', color: 'var(--on-error-cont)' }}
          >
            <Icon name="warning" size={14} />
            {warningCount} agent{warningCount !== 1 ? 's' : ''} need attention
          </span>
        )}
      </div>

      {/* Grid */}
      {isLoading ? (
        <p className="m3-body-medium" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          Loading agents…
        </p>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 gap-3">
          <Icon name="smart_toy" size={48} style={{ color: 'var(--on-sv)', opacity: 0.3 } as React.CSSProperties} />
          <p className="m3-body-medium" style={{ color: 'var(--on-sv)', opacity: 0.5 }}>
            No agents found. Start a session with <code>agentweave init</code>.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <MissionCard key={agent.name} agent={agent} />
          ))}
        </div>
      )}
    </div>
  )
}
