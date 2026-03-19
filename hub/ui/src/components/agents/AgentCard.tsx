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

interface AgentCardProps {
  agent: AgentSummary
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const cfg = STATUS_CONFIG[agent.status] ?? {
    dotColor: 'var(--border)', label: agent.status, pulse: false, labelColor: 'var(--on-sv)',
  }

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
        <span className="m3-label-small capitalize" style={{ color: cfg.labelColor }}>
          {cfg.label}
        </span>
      </div>
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
