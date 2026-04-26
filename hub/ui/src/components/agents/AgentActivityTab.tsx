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

  const activityItems: ActivityItem[] = useMemo(() => {
    const logItems: ActivityItem[] = outputLines
      .filter(line => SYSTEM_PREFIXES.some(prefix => line.content.startsWith(prefix)))
      .map(line => ({
        id: line.id,
        timestamp: line.timestamp,
        type: 'log',
        content: line.content,
      }))

    const eventItems: ActivityItem[] = timelineEvents.map(event => ({
      id: event.id,
      timestamp: event.timestamp,
      type: 'event',
      content: event.summary,
      eventType: event.event_type,
      summary: event.summary,
    }))

    const combined = [...logItems, ...eventItems]
    combined.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    return combined
  }, [outputLines, timelineEvents])

  useEffect(() => {
    if (shouldAutoScroll.current && scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [activityItems, isPaused])

  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 50
    shouldAutoScroll.current = isNearBottom
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--surface)' }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b shrink-0"
        style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-3">
          <Icon name="list_alt" size={20} style={{ color: 'var(--blue)' }} />
          <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>
            Activity — {agent.name}
          </span>
          <span
            className="text-[11px] px-2 py-0.5 rounded-full capitalize"
            style={{
              background: agent.status === 'running'
                ? 'rgba(34,197,94,0.1)'
                : 'rgba(161,161,170,0.1)',
              color: agent.status === 'running' ? 'var(--green)' : 'var(--text-3)',
            }}
          >
            {agent.status}
          </span>
        </div>
        <button
          onClick={() => setIsPaused(!isPaused)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-colors"
          style={{
            background: isPaused ? 'rgba(239,68,68,0.1)' : 'var(--surface-3)',
            color: isPaused ? 'var(--red)' : 'var(--text-3)',
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
          <div className="flex flex-col items-center justify-center h-full" style={{ color: 'var(--text-3)' }}>
            <Icon name="list_alt" size={48} style={{ opacity: 0.5, marginBottom: '1rem' }} />
            <p className="text-sm">No activity yet</p>
            <p className="text-xs mt-2" style={{ opacity: 0.7 }}>
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
          background: 'var(--surface-2)',
          borderLeft: '3px solid var(--blue)',
        }}
      >
        <Icon name="event_note" size={18} style={{ color: 'var(--blue)', marginTop: '2px' }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded uppercase"
              style={{
                background: 'rgba(59,130,246,0.1)',
                color: 'var(--blue)',
              }}
            >
              {item.eventType}
            </span>
            <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
              {timeAgo}
            </span>
          </div>
          <p className="text-sm mt-1" style={{ color: 'var(--text-3)' }}>
            {item.content}
          </p>
        </div>
      </div>
    )
  }

  const logIcon = item.content.includes('✅')
    ? 'check_circle'
    : item.content.includes('❌') || item.content.includes('error')
    ? 'error'
    : item.content.startsWith('[stderr]')
    ? 'terminal'
    : 'info'

  const logColor = item.content.includes('✅')
    ? 'var(--green)'
    : item.content.includes('❌') || item.content.includes('error')
    ? 'var(--red)'
    : item.content.startsWith('[stderr]')
    ? 'var(--amber)'
    : 'var(--blue)'

  return (
    <div
      className="flex items-start gap-3 p-3 rounded-lg"
      style={{
        background: 'var(--surface-2)',
        borderLeft: `3px solid ${logColor}`,
      }}
    >
      <Icon name={logIcon} size={18} style={{ color: logColor, marginTop: '2px' }} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded uppercase"
            style={{
              background: `${logColor}20`,
              color: logColor,
            }}
          >
            System
          </span>
          <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
            {timeAgo}
          </span>
        </div>
        <p className="text-sm mt-1" style={{ color: 'var(--text-3)' }}>
          {item.content}
        </p>
      </div>
    </div>
  )
}
