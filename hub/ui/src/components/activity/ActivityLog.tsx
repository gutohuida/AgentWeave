import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { SSEEvent, getBufferedEvents, useSSE } from '@/hooks/useSSE'
import { EventRow } from './EventRow'
import { EmptyState } from '@/components/common/EmptyState'
import { getJson } from '@/api/client'
import { useConfigStore } from '@/store/configStore'

type StoredEvent = SSEEvent & { localId: number }

const MAX_EVENTS = 200

const SEVERITY_FILTERS = ['all', 'error', 'warn', 'info', 'debug'] as const
type SeverityFilter = (typeof SEVERITY_FILTERS)[number]

const FILTER_ACTIVE_STYLE: Record<SeverityFilter, { bg: string; color: string }> = {
  all:   { bg: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  error: { bg: 'var(--error-cont)',      color: 'var(--on-error-cont)' },
  warn:  { bg: 'var(--t-cont)',          color: 'var(--on-t-cont)' },
  info:  { bg: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  debug: { bg: 'var(--surface-highest)', color: 'var(--on-sv)' },
}

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
        <h2 className="m3-title-medium" style={{ color: 'var(--foreground)' }}>Live Activity</h2>
        <button
          onClick={() => setPaused((p) => !p)}
          className="m3-chip-filter flex items-center gap-1.5"
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
              className={`m3-chip-filter capitalize${active ? ' active' : ''}`}
              style={active ? { background: style!.bg, color: style!.color, borderColor: 'transparent' } : undefined}
            >
              {active && <Icon name="check" size={14} />}
              {s}
            </button>
          )
        })}
      </div>

      {/* Event list */}
      <div
        className="flex-1 overflow-y-auto rounded-2xl p-3"
        style={{ background: 'var(--surface-low)', border: '1px solid var(--outline-variant)' }}
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
