import { useEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { hubDate } from '@/lib/hubTime'
import { useLogAgents, useLogs } from '@/api/logs'
import { Button } from '@/components/ui/button'
import { LogLine } from './LogLine'
import { useQueryClient } from '@tanstack/react-query'
import { tint } from '@/lib/colorTint'

const SEVERITIES = ['all', 'error', 'warn', 'info', 'debug'] as const
type Severity = (typeof SEVERITIES)[number]

const SEVERITY_ACTIVE_STYLE: Record<Severity, { bg: string; color: string }> = {
  all:   { bg: 'var(--surface-3)', color: 'var(--text)' },
  error: { bg: tint('var(--red)', 15), color: 'var(--red)' },
  warn:  { bg: tint('var(--amber)', 15), color: 'var(--amber)' },
  info:  { bg: 'var(--surface-3)', color: 'var(--text)' },
  debug: { bg: 'var(--surface-3)', color: 'var(--text-2)' },
}

const CATEGORIES = ['all', 'transport', 'watchdog', 'runner', 'proxy', 'setup', 'jobs', 'stderr'] as const
type Category = (typeof CATEGORIES)[number]

function eventCategory(eventType: string, data?: Record<string, unknown>): Category | 'other' {
  const category = typeof data?.category === 'string' ? data.category : ''
  const value = `${eventType} ${category}`.toLowerCase()
  if (value.includes('transport') || value.includes('hub_')) return 'transport'
  if (value.includes('watchdog')) return 'watchdog'
  if (value.includes('runner') || value.includes('launch') || value.includes('cli')) return 'runner'
  if (value.includes('proxy') || value.includes('api_key')) return 'proxy'
  if (value.includes('setup') || value.includes('sync') || value.includes('registration')) return 'setup'
  if (value.includes('job')) return 'jobs'
  if (value.includes('stderr')) return 'stderr'
  return 'other'
}

// The volume strip: 20 buckets over half an hour, derived from the entries already on screen
// rather than a second API call. With a 500-entry window rendered as a pure list, "did something
// spike five minutes ago" is otherwise unanswerable without scrolling — the one at-a-glance signal
// this screen has, and the only row of vertical space the design pass spends.
const VOLUME_BUCKETS   = 20
const VOLUME_WINDOW_MS = 30 * 60 * 1000
const VOLUME_BUCKET_MS = VOLUME_WINDOW_MS / VOLUME_BUCKETS

// A bucket takes the colour of the worst severity in it, mixed into --surface-3 rather than
// replacing it: the strip reads as one flat shape whose spikes are tinted, not as a chart with
// coloured series.
const VOLUME_BAR_ERROR = 'color-mix(in srgb, var(--red) 60%, var(--surface-3))'
const VOLUME_BAR_WARN  = 'color-mix(in srgb, var(--amber) 55%, var(--surface-3))'

// A single entry is not a spike. The callout only appears once a bucket holds enough to be worth
// the operator's eye, so a near-idle strip stays quiet.
const VOLUME_PEAK_MIN = 2

interface VolumeBucket {
  total: number
  error: number
  warn:  number
}

interface VolumeStrip {
  buckets:   VolumeBucket[]
  max:       number
  peakIndex: number
  peakRate:  number
  note:      string
}

function buildVolumeStrip(entries: { timestamp: string; severity?: string }[]): VolumeStrip | null {
  if (entries.length === 0) return null

  const now    = Date.now()
  const newest = entries.reduce((max, e) => Math.max(max, hubDate(e.timestamp).getTime()), 0)
  // Anchor on the newest entry when the feed has gone quiet. A wall-clock window would render an
  // empty strip for an idle project, which says nothing; anchored, the last half hour of actual
  // activity still answers the question — and the note below says which window it is, so the
  // reading is never a guess.
  const end   = newest > now - VOLUME_BUCKET_MS ? now : newest
  const start = end - VOLUME_WINDOW_MS

  const buckets: VolumeBucket[] = Array.from({ length: VOLUME_BUCKETS }, () => ({ total: 0, error: 0, warn: 0 }))
  for (const entry of entries) {
    const at = hubDate(entry.timestamp).getTime()
    if (at < start || at > end) continue
    const bucket = buckets[Math.min(VOLUME_BUCKETS - 1, Math.floor((at - start) / VOLUME_BUCKET_MS))]
    bucket.total += 1
    if (entry.severity === 'error') bucket.error += 1
    else if (entry.severity === 'warn') bucket.warn += 1
  }

  const max = buckets.reduce((hi, b) => Math.max(hi, b.total), 0)
  if (max === 0) return null

  const peakIndex = buckets.findIndex((b) => b.total === max)
  return {
    buckets,
    max,
    peakIndex,
    // Buckets are 90s wide, so the raw count is not a rate. Normalising to entries/minute is what
    // makes the number comparable to anything else the operator knows.
    peakRate: Math.max(1, Math.round(max / (VOLUME_BUCKET_MS / 60_000))),
    note: end === now ? 'last 30m' : `30m to ${format(new Date(end), 'HH:mm')}`,
  }
}

// Long enough for the arrival flash to finish (--dur-slow). Kept as a number because the class has
// to come back off the row: a row left flagged as new would re-flash the next time a filter change
// re-mounts it.
const ARRIVAL_FLASH_MS = 500

export function LogsView() {
  const [search,      setSearch]      = useState('')
  const [severity,    setSeverity]    = useState<Severity>('all')
  const [agentFilter, setAgentFilter] = useState('')
  const [category,    setCategory]    = useState<Category>('all')
  const [live,        setLive]        = useState(true)
  const [autoScroll,  setAutoScroll]  = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const bodyRef   = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  const { data: entries = [], isLoading, dataUpdatedAt } = useLogs({
    agent:    agentFilter || undefined,
    severity: severity !== 'all' ? severity : undefined,
    live,
  })
  const { data: logAgents = [] } = useLogAgents()

  const filtered = useMemo(() => {
    const byCategory = category === 'all'
      ? entries
      : entries.filter((e) => eventCategory(e.event_type, e.data) === category)
    if (!search.trim()) return byCategory
    const q = search.toLowerCase()
    return byCategory.filter((e) => {
      if (e.event_type.toLowerCase().includes(q)) return true
      if ((e.agent ?? '').toLowerCase().includes(q)) return true
      if (JSON.stringify(e.data ?? {}).toLowerCase().includes(q)) return true
      return false
    })
  }, [entries, search, category])

  const volume = useMemo(() => buildVolumeStrip(filtered), [filtered])

  // "New" means arrived, not rendered. The first payload seeds the seen-set silently — opening the
  // tab must not flash 500 rows — and an id, once seen, never counts as new again, so a filter
  // change that re-mounts old rows does not replay their arrival.
  const seenIdsRef = useRef<Set<string> | null>(null)
  const flashTimersRef = useRef<number[]>([])
  const [arrivedIds, setArrivedIds] = useState<ReadonlySet<string>>(() => new Set())

  useEffect(() => {
    const seen = seenIdsRef.current
    if (seen === null) {
      seenIdsRef.current = new Set(entries.map((e) => e.id))
      return
    }
    const fresh = entries.filter((e) => !seen.has(e.id)).map((e) => e.id)
    if (fresh.length === 0) return
    fresh.forEach((id) => seen.add(id))
    setArrivedIds((prev) => new Set([...prev, ...fresh]))
    flashTimersRef.current.push(window.setTimeout(() => {
      setArrivedIds((prev) => {
        const next = new Set(prev)
        fresh.forEach((id) => next.delete(id))
        return next
      })
    }, ARRIVAL_FLASH_MS))
  }, [entries])

  useEffect(() => () => {
    flashTimersRef.current.forEach((timer) => window.clearTimeout(timer))
    flashTimersRef.current = []
  }, [])

  useEffect(() => {
    if (live && autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'instant' })
  }, [dataUpdatedAt, live, autoScroll])

  function handleScroll() {
    const el = bodyRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoScroll(atBottom)
  }

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  // Deliberately `new Date`, not `hubDate`: `dataUpdatedAt` is React Query's own epoch
  // milliseconds, measured in this browser — not a timestamp the Hub serialised.
  const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'

  const chipBaseClassName = 'row-item w-auto whitespace-nowrap rounded-lg px-3 text-xs font-medium capitalize'

  const chipBase = {
    height: '32px',
    letterSpacing: '0.5px',
    border: '1px solid var(--border)',
    color: 'var(--text-3)',
    whiteSpace: 'nowrap',
    textTransform: 'capitalize',
  } as React.CSSProperties

  return (
    <div className="flex flex-col h-full" style={{ color: 'var(--text)' }}>
      {/* Toolbar */}
      <div
        className="flex flex-col gap-2 px-3 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div
            className="relative flex min-w-[180px] flex-1 items-center"
            style={{
              background: 'var(--surface-2)',
              borderRadius: 4,
              border: '1px solid var(--border)',
            }}
          >
            <Icon name="search" size={16} className="absolute left-2.5 pointer-events-none" style={{ color: 'var(--text-3)' }} />
            <input
              type="text"
              placeholder="Search event type, agent, data…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="control-field w-full h-8 pl-9 pr-3 text-xs bg-transparent"
              style={{ color: 'var(--text)' }}
            />
          </div>

          {/* Agent filter */}
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="control-field h-8 px-2 text-xs rounded"
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border-hi)',
              color: 'var(--text)',
              borderRadius: 4,
              width: 'auto',
              minWidth: 120,
              maxWidth: 180,
            }}
          >
            <option value="">All agents</option>
            {logAgents.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          {/* Refresh */}
          <Button variant="outline" size="icon-sm" onClick={refresh} title="Refresh" aria-label="Refresh">
            <Icon name="refresh" size={16} />
          </Button>

          {/* Live toggle */}
          <button
            onClick={() => setLive(!live)}
            data-active={live ? 'true' : 'false'}
            className="row-item h-8 w-auto gap-1.5 rounded-lg px-3 text-xs font-medium"
            style={{ border: '1px solid var(--border)' }}
          >
            {live && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />}
            {live ? 'Live' : 'Paused'}
          </button>
        </div>

        {/* Severity chips */}
        <div className="flex items-center gap-1.5">
          {SEVERITIES.map((s) => {
            const active = severity === s
            const style  = active ? SEVERITY_ACTIVE_STYLE[s] : undefined
            return (
              <button
                key={s}
                onClick={() => setSeverity(s)}
                className={chipBaseClassName}
                style={active ? { ...chipBase, background: style!.bg, color: style!.color, borderColor: 'transparent' } : chipBase}
              >
                {s}
              </button>
            )
          })}
          <span className="ml-auto text-[11px] tabular-nums" style={{ color: 'var(--text-3)', opacity: 0.7, fontFamily: "'JetBrains Mono', monospace" }}>
            {filtered.length.toLocaleString()} entr{filtered.length === 1 ? 'y' : 'ies'}
            {search ? ' (filtered)' : ''}
            {live && <span className="ml-2">· {lastUpdate}</span>}
          </span>
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto">
          {CATEGORIES.map((c) => {
            const active = category === c
            return (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={chipBaseClassName}
                style={active ? { ...chipBase, background: 'var(--surface-3)', color: 'var(--text)', borderColor: 'transparent' } : chipBase}
              >
                {c}
              </button>
            )
          })}
        </div>
      </div>

      {/* Volume strip — hidden while loading and when nothing is in the window, so it never
          occupies a row it has nothing to say in. */}
      {!isLoading && volume && (
        <div
          className="log-volume shrink-0"
          role="img"
          aria-label={`Log volume, ${volume.note}, peak ${volume.peakRate} entries per minute`}
        >
          <span className="log-volume-label">Volume</span>
          <div className="log-volume-bars">
            {volume.peakIndex >= 0 && volume.max >= VOLUME_PEAK_MIN && (
              <span
                className="log-volume-peak"
                style={{ left: `${((volume.peakIndex + 0.5) / VOLUME_BUCKETS) * 100}%` }}
              >
                {volume.peakRate}/min
              </span>
            )}
            {volume.buckets.map((bucket, index) => (
              <span
                key={index}
                className="log-volume-bar"
                // An empty bucket keeps a stub rather than vanishing: the baseline is what makes
                // the strip read as a timeline instead of a scatter of bars.
                style={{
                  height: `${bucket.total === 0 ? 6 : Math.max(10, Math.round((bucket.total / volume.max) * 100))}%`,
                  background: bucket.error > 0 ? VOLUME_BAR_ERROR : bucket.warn > 0 ? VOLUME_BAR_WARN : 'var(--surface-3)',
                }}
              />
            ))}
          </div>
          <span className="log-volume-note">{volume.note}</span>
        </div>
      )}

      {/* Log body */}
      <div
        ref={bodyRef}
        className="flex-1 overflow-auto"
        onScroll={handleScroll}
        style={{ background: 'var(--bg)' }}
      >
        {isLoading ? (
          <div className="space-y-2 p-3" aria-label="Loading log entries">
            {[0, 1, 2, 3, 4, 5].map((row) => <div key={row} className="skeleton h-6 w-full" aria-hidden="true" />)}
          </div>
        ) : filtered.length === 0 ? (
          <p className="font-mono text-xs p-4" style={{ color: 'var(--text-3)' }}>
            {search || severity !== 'all' || agentFilter
              ? 'No entries match the current filters.'
              : 'No log entries yet. Trigger some activity to see entries here.'}
          </p>
        ) : (
          <>
            {/* Sticky column header */}
            <div
              className="sticky top-0 z-10 flex items-center gap-2 px-2 py-1 font-mono text-[11px] select-none border-b"
              style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text-3)' }}
            >
              <span className="w-3 shrink-0" />
              <span className="shrink-0 w-[156px]">TIMESTAMP</span>
              <span className="shrink-0 w-12 text-center">SEV</span>
              <span className="shrink-0 w-44">EVENT TYPE</span>
              <span className="shrink-0 w-20">AGENT</span>
              <span className="flex-1">MESSAGE</span>
            </div>
            {filtered.map((entry) => (
              <LogLine key={entry.id} entry={entry} isNew={arrivedIds.has(entry.id)} />
            ))}
            <div ref={bottomRef} />
          </>
        )}
      </div>

      {/* Jump to latest nudge */}
      {live && !autoScroll && (
        <div
          className="shrink-0 flex justify-center py-1.5 border-t"
          style={{ borderColor: 'var(--border)' }}
        >
          <button
            onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }}
            className="text-xs font-medium flex items-center gap-1"
            style={{ color: 'var(--blue)' }}
          >
            <Icon name="arrow_downward" size={14} />
            Jump to latest
          </button>
        </div>
      )}
    </div>
  )
}
