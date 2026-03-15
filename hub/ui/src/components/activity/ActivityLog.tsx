import { useEffect, useRef, useState } from 'react'
import { Activity, Pause, Play } from 'lucide-react'
import { SSEEvent, getBufferedEvents, useSSE } from '@/hooks/useSSE'
import { EventRow } from './EventRow'
import { EmptyState } from '@/components/common/EmptyState'
import { getJson } from '@/api/client'
import { useConfigStore } from '@/store/configStore'

type StoredEvent = SSEEvent & { localId: number }

const MAX_EVENTS = 200

export function ActivityLog() {
  const counterRef = useRef(0)
  const { isConfigured } = useConfigStore()
  const [events, setEvents] = useState<StoredEvent[]>(() =>
    getBufferedEvents().map((e) => ({ ...e, localId: counterRef.current++ }))
  )
  const [paused, setPaused] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Load historical events from the EventLog table on mount
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
      .catch(() => {/* ignore — hub may not be reachable yet */})
  }, [isConfigured])

  useSSE((event) => {
    if (paused) return
    setEvents((prev) => {
      const next = [...prev, { ...event, localId: counterRef.current++ }]
      return next.slice(-MAX_EVENTS)
    })
  })

  useEffect(() => {
    if (!paused) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, paused])

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Live Activity</h2>
        <button
          onClick={() => setPaused((p) => !p)}
          className="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent"
        >
          {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto rounded-lg border bg-muted/10 p-3">
        {events.length === 0 ? (
          <EmptyState icon={Activity} title="Waiting for events…" description="SSE events will stream here in real time." />
        ) : (
          <>
            {[...events].reverse().map((event) => (
              <EventRow key={event.localId} event={event} />
            ))}
            <div ref={bottomRef} />
          </>
        )}
      </div>
    </div>
  )
}
