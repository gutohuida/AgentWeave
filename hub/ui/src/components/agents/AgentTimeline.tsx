import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { AgentSummary, useAgentTimeline } from '@/api/agents'

function iconForType(type: string): string {
  if (type === 'message')        return 'chat'
  if (type.startsWith('task'))   return 'task_alt'
  return 'bolt'
}

interface AgentTimelineProps {
  agent: AgentSummary
}

export function AgentTimeline({ agent }: AgentTimelineProps) {
  const { data: events = [], isLoading } = useAgentTimeline(agent.name)

  return (
    <div className="flex flex-col h-full overflow-auto p-4 gap-4">
      {/* Current activity banner */}
      {agent.latest_status_msg && (
        <div
          className="rounded-xl p-4"
          style={{
            border: '1px solid var(--border-hi)',
            background: 'var(--surface-2)',
          }}
        >
          <div className="flex items-center gap-2 text-xs font-medium mb-1" style={{ color: 'var(--text-3)' }}>
            <span className="h-2 w-2 rounded-full bg-current animate-pulse" style={{ color: 'var(--green)' }} />
            Current activity
          </div>
          <p className="text-sm" style={{ color: 'var(--text)' }}>{agent.latest_status_msg}</p>
        </div>
      )}

      {/* Timeline header */}
      <h3 className="text-sm font-medium" style={{ color: 'var(--text)' }}>Timeline</h3>

      {isLoading ? (
        <p className="text-sm" style={{ color: 'var(--text-3)' }}>Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-3)' }}>No timeline events yet.</p>
      ) : (
        <div className="space-y-1">
          {events.map((event) => {
            const iconName = iconForType(event.event_type)
            return (
              <div key={event.id} className="flex items-start gap-3" style={{ padding: '8px 0' }}>
                <div
                  className="shrink-0 flex items-center justify-center rounded-full"
                  style={{ width: 36, height: 36, background: 'var(--surface-3)', color: 'var(--text-2)' }}
                >
                  <Icon name={iconName} size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--text-3)' }}>
                    {event.event_type}
                  </p>
                  <p className="text-sm truncate" style={{ color: 'var(--text)' }}>{event.summary}</p>
                </div>
                <span className="text-[11px] whitespace-nowrap shrink-0" style={{ color: 'var(--text-3)' }}>
                  {formatDistanceToNow(new Date(event.timestamp), { addSuffix: true })}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
