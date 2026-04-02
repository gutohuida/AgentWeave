import { useEffect, useRef, useState, useMemo } from 'react'
import { useAgentOutput, useAgentTimeline, AgentSummary } from '@/api/agents'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'

interface AgentActivityTabProps {
  agent: AgentSummary
}

interface ActivityItem {
  id: string
  timestamp: string
  type: 'event' | 'log'
  content: string
  eventType?: string
  summary?: string
}

const SYSTEM_PREFIXES = ['[watchdog]', '[stderr]', '[session:']

export function AgentActivityTab({ agent }: AgentActivityTabProps) {
  const { lines: outputLines } = useAgentOutput(agent.name)
  const { data: timelineEvents = [] } = useAgentTimeline(agent.name)
  const [isPaused, setIsPaused] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const shouldAutoScroll = useRef(true)

  // Combine and sort activity items
  const activityItems: ActivityItem[] = useMemo(() => {
    // Convert output lines to activity items (filter to system lines only)
    const logItems: ActivityItem[] = outputLines
      .filter(line => SYSTEM_PREFIXES.some(prefix => line.content.startsWith(prefix)))
      .map(line => ({
        id: line.id,
        timestamp: line.timestamp,
        type: 'log',
        content: line.content,
      }))

    // Convert timeline events to activity items
    const eventItems: ActivityItem[] = timelineEvents.map(event => ({
      id: event.id,
      timestamp: event.timestamp,
      type: 'event',
      content: event.summary,
      eventType: event.event_type,
      summary: event.summary,
    }))

    // Combine and sort by timestamp
    const combined = [...logItems, ...eventItems]
    combined.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    return combined
  }, [outputLines, timelineEvents])

  // Auto-scroll to bottom
  useEffect(() => {
    if (shouldAutoScroll.current && scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [activityItems, isPaused])

  // Track user scroll to pause auto-scroll
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 50
    shouldAutoScroll.current = isNearBottom
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--surface-low)' }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b shrink-0"
        style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)' }}
      >
        <div className="flex items-center gap-3">
          <Icon name="list_alt" size={20} style={{ color: 'var(--primary)' }} />
          <span className="m3-title-small" style={{ color: 'var(--foreground)' }}>
            Activity — {agent.name}
          </span>
          <span
            className="m3-label-small px-2 py-0.5 rounded-full capitalize"
            style={{
              background: agent.status === 'running' 
                ? 'color-mix(in srgb, #22c55e 15%, transparent)'
                : 'color-mix(in srgb, var(--on-sv) 12%, transparent)',
              color: agent.status === 'running' ? '#22c55e' : 'var(--on-sv)',
            }}
          >
            {agent.status}
          </span>
        </div>
        <button
          onClick={() => setIsPaused(!isPaused)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg m3-label-small transition-colors"
          style={{
            background: isPaused ? 'var(--error-container)' : 'var(--surface)',
            color: isPaused ? 'var(--on-error-container)' : 'var(--on-sv)',
          }}
        >
          <Icon name={isPaused ? 'play_arrow' : 'pause'} size={18} />
          {isPaused ? 'Resume' : 'Pause'}
        </button>
      </div>

      {/* Activity Feed */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-2"
      >
        {activityItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--on-sv)' }}>
            <Icon name="list_alt" size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p className="m3-body-large">No activity yet</p>
            <p className="m3-body-small mt-2" style={{ opacity: 0.7 }}>
              Timeline events and system output will appear here
            </p>
          </div>
        ) : (
          activityItems.map((item) => (
            <ActivityRow key={item.id} item={item} />
          ))
        )}
      </div>
    </div>
  )
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const timeAgo = formatDistanceToNow(new Date(item.timestamp), { addSuffix: true })

  if (item.type === 'event') {
    return (
      <div
        className="flex items-start gap-3 p-3 rounded-lg"
        style={{
          background: 'var(--surface)',
          borderLeft: '3px solid var(--primary)',
        }}
      >
        <Icon name="event_note" size={18} style={{ color: 'var(--primary)', marginTop: '2px' }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="m3-label-small px-1.5 py-0.5 rounded uppercase"
              style={{
                background: 'color-mix(in srgb, var(--primary) 15%, transparent)',
                color: 'var(--primary)',
                fontSize: '0.65rem',
              }}
            >
              {item.eventType}
            </span>
            <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
              {timeAgo}
            </span>
          </div>
          <p className="m3-body-medium mt-1" style={{ color: 'var(--on-sv)' }}>
            {item.content}
          </p>
        </div>
      </div>
    )
  }

  // Log item - card style matching events
  const logIcon = item.content.includes('✅') 
    ? 'check_circle' 
    : item.content.includes('❌') || item.content.includes('error') 
    ? 'error' 
    : item.content.startsWith('[stderr]')
    ? 'terminal'
    : 'info'

  const logColor = item.content.includes('✅')
    ? '#22c55e'
    : item.content.includes('❌') || item.content.includes('error')
    ? 'var(--error)'
    : item.content.startsWith('[stderr]')
    ? 'var(--tertiary)'
    : 'var(--primary)'

  return (
    <div
      className="flex items-start gap-3 p-3 rounded-lg"
      style={{
        background: 'var(--surface)',
        borderLeft: `3px solid ${logColor}`,
      }}
    >
      <Icon name={logIcon} size={18} style={{ color: logColor, marginTop: '2px' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="m3-label-small px-1.5 py-0.5 rounded uppercase"
            style={{
              background: `color-mix(in srgb, ${logColor} 15%, transparent)`,
              color: logColor,
              fontSize: '0.65rem',
            }}
          >
            System
          </span>
          <span className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
            {timeAgo}
          </span>
        </div>
        <p className="m3-body-medium mt-1" style={{ color: 'var(--on-sv)' }}>
          {item.content}
        </p>
      </div>
    </div>
  )
}
