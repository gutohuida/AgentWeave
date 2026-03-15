import { formatDistanceToNow } from 'date-fns'
import { AgentSummary } from '@/api/agents'
import { cn } from '@/lib/utils'

interface StatusConfig {
  dot: string
  label: string
  pulse: boolean
  labelColor: string
}

const STATUS_CONFIG: Record<string, StatusConfig> = {
  running: { dot: 'bg-emerald-400', label: 'Running', pulse: true,  labelColor: 'text-emerald-400 font-semibold' },
  active:  { dot: 'bg-emerald-400', label: 'Active',  pulse: false, labelColor: 'text-emerald-400' },
  idle:    { dot: 'bg-white/20',    label: 'Idle',    pulse: false, labelColor: 'text-white/30' },
  waiting: { dot: 'bg-amber-400',   label: 'Waiting', pulse: false, labelColor: 'text-amber-400' },
}

interface AgentCardProps {
  agent: AgentSummary
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, selected, onClick }: AgentCardProps) {
  const cfg = STATUS_CONFIG[agent.status] ?? { dot: 'bg-white/20', label: agent.status, pulse: false, labelColor: 'text-white/30' }

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-xl p-3 transition-all',
        selected
          ? 'glass-accent'
          : 'glass-card'
      )}
    >
      <div className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          {cfg.pulse && (
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-75`} />
          )}
          <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${cfg.dot}`} />
        </span>
        <span className={cn('font-medium text-sm', cfg.pulse ? 'text-white font-bold' : 'text-white/80')}>{agent.name}</span>
        <span className={cn('ml-auto text-xs capitalize', cfg.labelColor)}>
          {cfg.label}
        </span>
      </div>
      <div className="mt-1.5 flex gap-3 text-xs text-white/25">
        <span>{agent.message_count} msgs</span>
        <span>{agent.active_task_count} tasks</span>
        {agent.last_seen && (
          <span className="ml-auto">
            {formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })}
          </span>
        )}
      </div>
      {agent.latest_status_msg && (
        <p className="mt-1 text-xs text-white/35 truncate">{agent.latest_status_msg}</p>
      )}
    </button>
  )
}
