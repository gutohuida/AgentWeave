import { useMemo, useState } from 'react'
import type { AgentOutputLine } from '@/api/agents'
import { formatStreamDuration, normalizeStreamEvent } from './streamModel'

export function SharedStreamRenderer({
  lines,
  showDiagnostics = true,
}: {
  lines: AgentOutputLine[]
  showDiagnostics?: boolean
}) {
  const events = useMemo(() => {
    const grouped = lines.map(normalizeStreamEvent).reduce<Array<ReturnType<typeof normalizeStreamEvent> & { endTimestamp?: string }>>((items, event) => {
      const previous = items[items.length - 1]
      if (event.kind === 'thinking' && previous?.kind === 'thinking' && previous.run_id === event.run_id) {
        previous.content = `${previous.content}\n${event.content}`
        previous.endTimestamp = event.timestamp
        return items
      }
      items.push({ ...event })
      return items
    }, [])
    return grouped
  }, [lines])
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  return <div className="space-y-1">
    {events.map((event, index) => {
      if (event.kind === 'diagnostic' && !showDiagnostics) return null
      const key = event.id ?? `${event.run_id ?? 'legacy'}-${event.sequence ?? index}`
      const next = events[index + 1]
      const thinkingLive = event.kind === 'thinking' && !next && Boolean(event.run_id)
      const paired = event.kind === 'tool_use' && event.callId
        ? events.find((candidate) => candidate.kind === 'tool_result' && candidate.run_id === event.run_id && candidate.callId === event.callId)
        : undefined
      const isExpandable = event.kind === 'thinking' || event.kind === 'tool_use' || event.kind === 'tool_result'
      const color = event.kind === 'error' ? 'var(--red)'
        : event.kind === 'diagnostic' ? 'var(--amber)'
        : event.kind === 'status' ? 'var(--blue)'
        : 'var(--text)'
      return <div key={key} data-stream-kind={event.kind} className="font-mono text-xs leading-5 break-words" style={{ color }}>
        {isExpandable ? (
          <button className="text-left w-full" onClick={() => setExpanded((old) => ({ ...old, [key]: !old[key] }))}>
            <span style={{ color: 'var(--text-3)' }}>
              {event.kind === 'thinking' ? (thinkingLive ? 'Thinking…' : 'Thinking') : event.kind.replace('_', ' ')}
              {event.kind === 'thinking' && event.endTimestamp ? ` · ${formatStreamDuration(event.timestamp, event.endTimestamp)}` : ''}
              {paired ? ` · ${paired.payload?.is_error === true ? 'failed' : 'completed'}` : event.kind === 'tool_use' ? ' · awaiting result' : ''}
            </span>
            {(expanded[key] || thinkingLive || event.kind !== 'thinking') && <span className="block whitespace-pre-wrap">{event.content}</span>}
            {expanded[key] && event.payload && <pre className="whitespace-pre-wrap" style={{ color: 'var(--text-3)' }}>{JSON.stringify(event.payload, null, 2)}</pre>}
          </button>
        ) : <span className="whitespace-pre-wrap">{event.content}</span>}
      </div>
    })}
  </div>
}
