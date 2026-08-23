import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { getBufferedEvents, useSSE } from '@/hooks/useSSE'
import { EventRow } from './EventRow'
import { EmptyState } from '@/components/common/EmptyState'
import { getJson } from '@/api/client'
import { useConfigStore } from '@/store/configStore'
import { useAgents } from '@/api/agents'
import { tint } from '@/lib/colorTint'

interface SSEEvent {
  type: string
  data: unknown
  timestamp: string
  severity?: string
}

type StoredEvent = SSEEvent & { localId: number }

function eventActor(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const record = data as Record<string, unknown>
  for (const key of ['agent', 'actor', 'from', 'assignee']) {
    if (typeof record[key] === 'string' && record[key]) return record[key]
  }
  return null
}

const MAX_EVENTS = 200

const SEVERITY_FILTERS = ['all', 'error', 'warn', 'info', 'debug'] as const
type SeverityFilter = (typeof SEVERITY_FILTERS)[number]

// Via the shared tint() helper rather than a second hand-written color-mix(): same computed
// colour, one implementation, and it follows the token across the light/dark ramp.
const FILTER_ACTIVE_STYLE: Record<SeverityFilter, { bg: string; color: string }> = {
  all:   { bg: 'var(--surface-3)', color: 'var(--text)' },
  error: { bg: tint('var(--red)', 15), color: 'var(--red)' },
  warn:  { bg: tint('var(--amber)', 15), color: 'var(--amber)' },
  info:  { bg: 'var(--surface-3)', color: 'var(--text)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-2)' },
}

// The chip's geometry, motion and interaction states live in `.activity-chip` (index.css). The
// inline object this replaced set `background: 'transparent'`, which — being inline — beat the
// global [role=button] hover rule and left every chip and the Pause button dead to the pointer.
// Only the active chip's *colours* stay in TS, because they are per-severity data; they are handed
// to CSS as custom properties so the hover rule can still paint over them.
function activeChipVars(filter: SeverityFilter): React.CSSProperties {
  const { bg, color } = FILTER_ACTIVE_STYLE[filter]
  return { '--chip-bg': bg, '--chip-fg': color } as React.CSSProperties
}

// Matches --dur-slow, the arrival flash's duration; the class has to come back off the row so a
// re-render never replays it.
const ARRIVAL_FLASH_MS = 500

export function ActivityLog() {
  const counterRef = useRef(0)
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const { data: agents = [] } = useAgents()
  const colorsByAgent = new Map(agents.map((agent) => [agent.name, agent.color_index]))
  const [events, setEvents] = useState<StoredEvent[]>(() =>
    getBufferedEvents()
      .filter((e) => (e.data as { project_id?: string } | null)?.project_id === projectId)
      .map((e) => ({ ...e, localId: counterRef.current++ }))
  )
  const [paused, setPaused] = useState(false)
  // Defensive: useSSE registers the callback once and dispatches from a ref
  // internally, but mirroring the AGENTS.md "stale closure" pattern protects
  // against future refactors of useSSE.
  const pausedRef = useRef(paused)
  useEffect(() => {
    pausedRef.current = paused
  }, [paused])
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all')
  const [loadingHistory, setLoadingHistory] = useState(false)
  const tailRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [atTail, setAtTail] = useState(true)

  // Arrival is read off the SSE callback, the only path an event can genuinely *arrive* on: the
  // history fetch backfills rows that already happened, and flashing 200 of those on tab open
  // would say nothing. The flag is dropped again after the animation so a re-render cannot replay
  // it and a re-mount cannot resurrect it.
  const [arrivedIds, setArrivedIds] = useState<ReadonlySet<number>>(() => new Set())
  const flashTimersRef = useRef<number[]>([])

  function markArrived(localId: number) {
    setArrivedIds((prev) => new Set([...prev, localId]))
    flashTimersRef.current.push(window.setTimeout(() => {
      setArrivedIds((prev) => {
        const next = new Set(prev)
        next.delete(localId)
        return next
      })
    }, ARRIVAL_FLASH_MS))
  }

  useEffect(() => () => {
    flashTimersRef.current.forEach((timer) => window.clearTimeout(timer))
    flashTimersRef.current = []
  }, [])

  useEffect(() => {
    if (!isConfigured || !projectId) return
    let cancelled = false
    setEvents([])
    // Emptying the list resets the container's scrollTop without firing a scroll event, so the
    // follow flag has to be reset by hand or the new project opens already detached from its tail.
    setAtTail(true)
    setLoadingHistory(true)
    getJson<SSEEvent[]>(`/api/v1/projects/${projectId}/events/history?limit=200`)
      .then((history) => {
        if (cancelled) return
        setEvents((prev) => {
          const existingIds = new Set(prev.map((e) => e.timestamp + e.type))
          const fresh = history
            .filter((e) => !existingIds.has(e.timestamp + e.type))
            .map((e) => ({ ...e, localId: counterRef.current++ }))
          return [...fresh, ...prev].slice(-MAX_EVENTS)
        })
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingHistory(false)
      })
    return () => {
      cancelled = true
    }
  }, [isConfigured, projectId])

  // The shared SSE stream is instance-wide (every project's events, per
  // hub/hub/sse.py's operator fan-out) — filter to the selected project so
  // switching projects doesn't blend two projects' activity into one feed.
  useSSE((event) => {
    if (pausedRef.current) return
    const d = (event.data ?? {}) as { project_id?: string }
    if (d.project_id !== projectId) return
    // The id is minted outside the updater: React may invoke an updater twice, and a doubled
    // counter would break the arrival flag's pairing with the row it belongs to.
    const localId = counterRef.current++
    setEvents((prev) => [...prev, { ...event, localId }].slice(-MAX_EVENTS))
    markArrived(localId)
  })

  // This feed renders newest-first, so the tail it must follow is the TOP of the list. The anchor
  // used to sit after the map — below 200 buffered events — so every arrival scrolled the operator
  // away from the thing that had just arrived. Following only while the operator is already at the
  // tail is LogsView's rule, for the same reason: scrolling back through history must not be
  // yanked out from under them.
  useEffect(() => {
    if (paused || !atTail) return
    tailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [events, paused, atTail])

  function handleScroll() {
    const el = listRef.current
    if (!el) return
    setAtTail(el.scrollTop < 40)
  }

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
          className="activity-chip"
        >
          <Icon name={paused ? 'play_arrow' : 'pause'} size={16} />
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>

      {/* Severity filters */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {SEVERITY_FILTERS.map((s) => {
          const active = severityFilter === s
          return (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className="activity-chip"
              data-active={active ? 'true' : 'false'}
              aria-pressed={active}
              style={active ? activeChipVars(s) : undefined}
            >
              {active && <Icon name="check" size={14} />}
              {s}
            </button>
          )
        })}
      </div>

      {/* Event list */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto rounded-xl p-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        {loadingHistory ? (
          <div className="space-y-3" aria-label="Loading activity">
            {[0, 1, 2, 3, 4].map((row) => (
              <div key={row} className="flex items-center gap-3" aria-hidden="true">
                <div className="skeleton h-9 w-9 rounded-full" />
                <div className="skeleton h-8 flex-1" />
              </div>
            ))}
          </div>
        ) : visibleEvents.length === 0 ? (
          <EmptyState icon="monitoring" title="Waiting for events…" description="SSE events will stream here in real time." />
        ) : (
          <>
            <div ref={tailRef} data-testid="activity-tail-anchor" />
            {[...visibleEvents].reverse().map((event) => (
              <EventRow
                key={event.localId}
                event={event}
                actorName={eventActor(event.data)}
                actorColorIndex={colorsByAgent.get(eventActor(event.data) ?? '')}
                isNew={arrivedIds.has(event.localId)}
              />
            ))}
          </>
        )}
      </div>

      {/* Jump to latest — the same nudge LogsView offers once the operator has scrolled off the
          tail, pointing the other way because the tail here is the top. */}
      {!paused && !atTail && (
        <button
          onClick={() => { setAtTail(true); tailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }}
          className="shrink-0 self-center flex items-center gap-1 text-xs font-medium"
          style={{ color: 'var(--blue)' }}
        >
          <Icon name="arrow_upward" size={14} />
          Jump to latest
        </button>
      )}
    </div>
  )
}
