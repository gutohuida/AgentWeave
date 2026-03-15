import { useEffect, useRef, useState } from 'react'
import { Activity, Pause, Play } from 'lucide-react'
import { SSEEvent, getBufferedEvents, useSSE } from '@/hooks/useSSE'
import { EventRow } from './EventRow'
import { EmptyState } from '@/components/common/EmptyState'
import { getJson } from '@/api/client'
import { useConfigStore } from '@/store/configStore'

type StoredEvent = SSEEvent & { localId: number }

const MAX_EVENTS = 200

const SEVERITY_FILTERS = ['all', 'error', 'warn', 'info', 'debug'] as const
type SeverityFilter = (typeof SEVERITY_FILTERS)[number]

const PILL_ACTIVE: Record<SeverityFilter, string> = {
  all:   'bg-white/10 text-white ring-1 ring-white/20',
  error: 'bg-red-500/15 text-red-400 ring-1 ring-red-500/20',
  warn:  'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
  info:  'bg-primary/15 text-primary ring-1 ring-primary/20',
  debug: 'bg-white/[0.06] text-white/40 ring-1 ring-white/10',
}
const PILL_INACTIVE = 'text-white/30 hover:text-white/60 hover:bg-white/[0.05]'

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
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white/80">Live Activity</h2>
        <button
          onClick={() => setPaused((p) => !p)}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-white/50 hover:text-white/80 transition-colors"
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.10)' }}
        >
          {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        {SEVERITY_FILTERS.map((s) => (
          <button
            key={s}
            onClick={() => setSeverityFilter(s)}
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize transition-colors ${
              severityFilter === s ? PILL_ACTIVE[s] : PILL_INACTIVE
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto rounded-xl p-3" style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.07)' }}>
        {visibleEvents.length === 0 ? (
          <EmptyState icon={Activity} title="Waiting for events…" description="SSE events will stream here in real time." />
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
