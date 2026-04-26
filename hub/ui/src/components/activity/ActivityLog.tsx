import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { getBufferedEvents, useSSE } from '@/hooks/useSSE'
import { EventRow } from './EventRow'
import { EmptyState } from '@/components/common/EmptyState'
import { getJson } from '@/api/client'
import { useConfigStore } from '@/store/configStore'

interface SSEEvent {
  type: string
  data: unknown
  timestamp: string
  severity?: string
}

type StoredEvent = SSEEvent & { localId: number }

const MAX_EVENTS = 200

const SEVERITY_FILTERS = ['all', 'error', 'warn', 'info', 'debug'] as const
type SeverityFilter = (typeof SEVERITY_FILTERS)[number]

const FILTER_ACTIVE_STYLE: Record<SeverityFilter, { bg: string; color: string }> = {
  all:   { bg: 'var(--surface-3)', color: 'var(--text)' },
  error: { bg: 'rgba(239,68,68,0.15)', color: 'var(--red)' },
  warn:  { bg: 'rgba(245,158,11,0.15)', color: 'var(--amber)' },
  info:  { bg: 'var(--surface-3)', color: 'var(--text)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-2)' },
}

const chipBase = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
  height: '32px',
  borderRadius: '8px',
  padding: '0 12px',
  fontSize: '12px',
  fontWeight: 500,
  letterSpacing: '0.5px',
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'var(--text-3)',
  transition: 'background-color 0.15s, border-color 0.15s, color 0.15s',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  textTransform: 'capitalize',
} as React.CSSProperties

export function ActivityLog() {
  const counterRef = useRef(0)
  const { isConfigured } = useConfigStore()
  const [events, setEvents] = useState<StoredEvent[]>(() =>
    getBufferedEvents().map((e) => ({ ...e, localId: counterRef.current++ }))
  )
  const [paused, setPaused] = useState(false)
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isConfigured) return
    getJson<SSEEvent[]>('/api/v1/events/history?limit=200')
      .then((history) => {
        setEvents((prev) => {
          const existingIds = new Set(prev.map((e) => e.timestamp + e.type))
          const fresh = history
            .filter((e) => !existingIds.has(e.timestamp + e.type))
            .map((e) => ({ ...e, localId: counterRef.current++ }))
          return [...fresh, ...prev].slice(-MAX_EVENTS)
        })
      })
      .catch(() => {})
  }, [isConfigured])

  useSSE((event) => {
    if (paused) return
    setEvents((prev) => {
      const next = [...prev, { ...event, localId: counterRef.current++ }]
      return next.slice(-MAX_EVENTS)
    })
  })

  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, paused])

  const visibleEvents = severityFilter === 'all'
    ? events
    : events.filter((e) => e.severity === severityFilter)

  return (
    <div className="flex flex-col h-full p-4 gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium" style={{ color: 'var(--text)' }}>Live Activity</h2>
        <button
          onClick={() => setPaused((p) => !p)}
          style={chipBase}
        >
          <Icon name={paused ? 'play_arrow' : 'pause'} size={16} />
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      {/* Severity filters */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {SEVERITY_FILTERS.map((s) => {
          const active = severityFilter === s
          const style  = active ? FILTER_ACTIVE_STYLE[s] : undefined
          return (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              style={active ? { ...chipBase, background: style!.bg, color: style!.color, borderColor: 'transparent' } : chipBase}
            >
              {active && <Icon name="check" size={14} />}
              {s}
            </button>
          )
        })}
      </div>

      {/* Event list */}
      <div
        className="flex-1 overflow-y-auto rounded-xl p-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        {visibleEvents.length === 0 ? (
          <EmptyState icon="monitoring" title="Waiting for events…" description="SSE events will stream here in real time." />
        ) : (
          <>
            {[...visibleEvents].reverse().map((event) => (
              <EventRow key={event.localId} event={event} />
            ))}
            <div ref={bottomRef} />
          </>
        )}
      </div>
    </div>
  )
}
