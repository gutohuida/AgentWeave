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
          className="m3-status-banner"
          style={{
            borderColor:     'color-mix(in srgb, var(--primary) 30%, transparent)',
            backgroundColor: 'color-mix(in srgb, var(--primary) 5%, var(--surface-low))',
          }}
        >
          <div className="flex items-center gap-2 m3-label-medium mb-1" style={{ color: 'var(--on-sv)' }}>
            <span className="h-2 w-2 rounded-full bg-current animate-pulse" style={{ color: '#22c55e' }} />
            Current activity
          </div>
          <p className="m3-body-medium" style={{ color: 'var(--foreground)' }}>{agent.latest_status_msg}</p>
        </div>
      )}

      {/* Timeline header */}
      <h3 className="m3-title-medium" style={{ color: 'var(--foreground)' }}>Timeline</h3>

      {isLoading ? (
        <p className="m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading…</p>
      ) : events.length === 0 ? (
        <p className="m3-body-medium" style={{ color: 'var(--on-sv)' }}>No timeline events yet.</p>
      ) : (
        <div className="space-y-1">
          {events.map((event) => {
            const iconName = iconForType(event.event_type)
            return (
              <div key={event.id} className="m3-list-item-2" style={{ gap: 12, padding: '8px 0' }}>
                {/* Icon in tonal container */}
                <div
                  className="m3-icon-container shrink-0"
                  style={{ width: 36, height: 36, background: 'var(--p-cont)', color: 'var(--on-p-cont)' }}
                >
                  <Icon name={iconName} size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="m3-label-medium uppercase tracking-wide" style={{ color: 'var(--on-sv)' }}>
                    {event.event_type}
                  </p>
                  <p className="m3-body-medium truncate" style={{ color: 'var(--foreground)' }}>{event.summary}</p>
                </div>
                <span className="m3-label-small whitespace-nowrap shrink-0" style={{ color: 'var(--on-sv)' }}>
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
