import { formatDistanceToNow } from 'date-fns'
import { AgentSummary } from '@/api/agents'

interface StatusConfig {
  dotColor: string
  label: string
  pulse: boolean
  labelColor: string
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  running: { dotColor: '#22c55e', label: 'Running', pulse: true,  labelColor: 'var(--primary)' },
  active:  { dotColor: '#22c55e', label: 'Active',  pulse: false, labelColor: 'var(--primary)' },
  idle:    { dotColor: 'var(--border)', label: 'Idle', pulse: false, labelColor: 'var(--on-sv)' },
  waiting: { dotColor: '#f59e0b', label: 'Waiting', pulse: false, labelColor: 'var(--on-t-cont)' },
}

const ROLE_CONFIG: Record<string, { bg: string; color: string }> = {
  principal:    { bg: 'color-mix(in srgb, #3b82f6 15%, transparent)', color: '#3b82f6' },
  delegate:     { bg: 'color-mix(in srgb, #22c55e 15%, transparent)', color: '#22c55e' },
  collaborator: { bg: 'color-mix(in srgb, var(--on-sv) 12%, transparent)', color: 'var(--on-sv)' },
}

const RUNNER_CONFIG: Record<string, { bg: string; color: string; label: string }> = {
  claude_proxy: {
    bg: 'color-mix(in srgb, #f59e0b 15%, transparent)',
    color: '#f59e0b',
    label: 'proxy'
  },
  manual: {
    bg: 'color-mix(in srgb, #6b7280 15%, transparent)',
    color: '#6b7280',
    label: 'manual'
  },
}

interface AgentCardProps {
  agent: AgentSummary
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const cfg = STATUS_CONFIG[agent.status] ?? {
    dotColor: 'var(--border)', label: agent.status, pulse: false, labelColor: 'var(--on-sv)',
  }
  const roleCfg = agent.role ? (ROLE_CONFIG[agent.role] ?? ROLE_CONFIG.collaborator) : null

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl p-3 transition-all"
      style={{
        background:   selected
          ? 'color-mix(in srgb, var(--p-cont) 50%, var(--surface-highest))'
          : 'var(--surface-highest)',
        border:       `1px solid ${selected ? 'color-mix(in srgb, var(--primary) 35%, transparent)' : 'var(--outline-variant)'}`,
        boxShadow:    selected ? 'var(--elev-1)' : 'none',
      }}
    >
      <div className="flex items-center gap-2">
        {/* Status dot */}
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
          className="m3-title-small flex-1 text-left"
          style={{ color: 'var(--foreground)', fontWeight: cfg.pulse ? 600 : 500 }}
        >
          {agent.name}
        </span>
        {/* Yolo indicator */}
        {agent.yolo && (
          <span
            title="Yolo mode — running without permission prompts"
            className="material-symbols-rounded select-none"
            style={{ fontSize: 16, color: '#f59e0b' }}
          >
            bolt
          </span>
        )}
        <span className="m3-label-small capitalize" style={{ color: cfg.labelColor }}>
          {cfg.label}
        </span>
      </div>
      {/* Role badges */}
      {(roleCfg || agent.dev_roles?.length || agent.dev_role || agent.runner) && (
        <div className="mt-1.5 flex gap-1.5 flex-wrap">
          {roleCfg && (
            <span
              className="m3-label-small capitalize px-1.5 py-0.5 rounded-full"
              style={{ background: roleCfg.bg, color: roleCfg.color, fontSize: '0.65rem' }}
            >
              {agent.role}
            </span>
          )}
          {/* Multiple dev roles (new format) */}
          {agent.dev_roles?.map((role, idx) => (
            <span
              key={role}
              className="m3-label-small px-1.5 py-0.5 rounded-full"
              title={`Dev role: ${role}`}
              style={{
                background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                color: '#8b5cf6',
                fontSize: '0.65rem',
              }}
            >
              {agent.dev_role_labels?.[idx] ?? role}
            </span>
          ))}
          {/* Single dev role (legacy format - fallback) */}
          {!agent.dev_roles?.length && agent.dev_role && (
            <span
              className="m3-label-small px-1.5 py-0.5 rounded-full"
              title={`Dev role: ${agent.dev_role}`}
              style={{
                background: 'color-mix(in srgb, #8b5cf6 15%, transparent)',
                color: '#8b5cf6',
                fontSize: '0.65rem',
              }}
            >
              {agent.dev_role_label ?? agent.dev_role}
            </span>
          )}
          {agent.runner && agent.runner !== 'native' && (
            <span
              className="m3-label-small capitalize px-1.5 py-0.5 rounded-full"
              style={{
                background: RUNNER_CONFIG[agent.runner]?.bg || RUNNER_CONFIG.manual.bg,
                color: RUNNER_CONFIG[agent.runner]?.color || RUNNER_CONFIG.manual.color,
                fontSize: '0.65rem'
              }}
            >
              {RUNNER_CONFIG[agent.runner]?.label || agent.runner}
            </span>
          )}
        </div>
      )}
      <div className="mt-1.5 flex gap-3 m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
        <span>{agent.message_count} msgs</span>
        <span>{agent.active_task_count} tasks</span>
        {agent.last_seen && (
          <span className="ml-auto">
            {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </span>
        )}
      </div>
      {agent.latest_status_msg && (
        <p className="mt-1 m3-body-small truncate" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
          {agent.latest_status_msg}
        </p>
      )}
    </button>
  )
}
