import { formatDistanceToNow } from 'date-fns'
import { AgentSummary } from '@/api/agents'
import { contextBarColor, getStatusConfig, StatusDot, DevRoleTagList } from '@/lib/agentStatus'

interface AgentCardProps {
  agent: AgentSummary
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const cfg = getStatusConfig(agent.status)
  const ctx = agent.context_usage

  return (
    <button
      onClick={onClick}
      className="w-full text-left"
      style={{
        background: selected ? 'rgba(255,255,255,0.05)' : 'var(--surface-2)',
        border: `1px solid ${selected ? 'var(--border-hi)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        padding: 10,
        cursor: 'pointer',
        transition: 'background 0.15s, border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        if (!selected) e.currentTarget.style.borderColor = 'var(--border-hi)'
      }}
      onMouseLeave={(e) => {
        if (!selected) e.currentTarget.style.borderColor = 'var(--border)'
      }}
    >
      <div className="flex items-center gap-2">
        {/* Status dot */}
        <StatusDot status={agent.status} size="sm" />
        <span
          className="flex-1 text-left text-sm font-medium truncate"
          style={{ color: 'var(--text)' }}
        >
          {agent.name}
        </span>
        {/* Yolo indicator */}
        {agent.yolo && (
          <span title="Yolo mode" style={{ fontSize: 12, color: 'var(--amber)' }}>⚡</span>
        )}
        <span className="text-xs capitalize shrink-0" style={{ color: cfg.labelColor }}>
          {cfg.label}
        </span>
      </div>

      {/* Role badges */}
      {(agent.dev_roles?.length || agent.dev_role || agent.runner) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <DevRoleTagList agent={agent} />
          {agent.display_model && (
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(161,161,170,0.1)', color: 'var(--text-2)' }}
            >
              {agent.display_model}
            </span>
          )}
          {agent.self_registered && (
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(34,197,94,0.1)', color: 'var(--green)' }}
            >
              EXT
            </span>
          )}
          {agent.pilot && (
            <span
              className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(236,72,153,0.1)', color: '#ec4899' }}
            >
              PILOT
            </span>
          )}
        </div>
      )}

      {/* Stats row */}
      <div className="mt-1.5 flex items-center gap-3 text-[11px]" style={{ color: 'var(--text-3)' }}>
        <span>{agent.message_count} msgs</span>
        <span>{agent.active_task_count} tasks</span>
        {agent.last_seen && (
          <span className="ml-auto">
            {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </span>
        )}
      </div>

      {/* Context bar */}
      {ctx && ctx.percent != null && (
        <div className="mt-1.5 w-full rounded-full overflow-hidden" style={{ height: 2, background: 'var(--surface-3)' }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(100, Math.max(0, ctx.percent))}%`,
              background: contextBarColor(ctx.percent, !!(ctx.warning || ctx.critical)),
            }}
          />
        </div>
      )}

      {agent.latest_status_msg && (
        <p className="mt-1 truncate text-[11px]" style={{ color: 'var(--text-3)' }}>
          {agent.latest_status_msg}
        </p>
      )}
    </button>
  )
}
