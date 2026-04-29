import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useLogAgents, useLogs } from '@/api/logs'
import { LogLine } from './LogLine'
import { useQueryClient } from '@tanstack/react-query'

const SEVERITIES = ['all', 'error', 'warn', 'info', 'debug'] as const
type Severity = (typeof SEVERITIES)[number]

const SEVERITY_ACTIVE_STYLE: Record<Severity, { bg: string; color: string }> = {
  all:   { bg: 'var(--surface-3)', color: 'var(--text)' },
  error: { bg: 'rgba(239,68,68,0.15)', color: 'var(--red)' },
  warn:  { bg: 'rgba(245,158,11,0.15)', color: 'var(--amber)' },
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

  const lastUpdate = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'

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

  return (
    <div className="flex flex-col h-full" style={{ color: 'var(--text)' }}>
      {/* Toolbar */}
      <div
        className="flex flex-col gap-2 px-3 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          {/* Search */}
          <div
            className="relative flex-1 flex items-center"
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
              className="w-full h-8 pl-9 pr-3 text-xs focus:outline-none bg-transparent"
              style={{ color: 'var(--text)' }}
            />
          </div>

          {/* Agent filter */}
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="h-8 px-2 text-xs focus:outline-none rounded"
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border-hi)',
              color: 'var(--text)',
              borderRadius: 4,
            }}
          >
            <option value="">All agents</option>
            {logAgents.map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          {/* Refresh */}
          <button
            onClick={refresh}
            className="flex items-center justify-center shrink-0"
            style={{ width: 32, height: 32, border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-3)', background: 'transparent', cursor: 'pointer' }}
            title="Refresh"
          >
            <Icon name="refresh" size={16} />
          </button>

          {/* Live toggle */}
          <button
            onClick={() => setLive(!live)}
            className="flex items-center gap-1.5 h-8 rounded-lg px-3 text-xs font-medium transition-colors border"
            style={{
              background:   live ? 'var(--surface-3)' : 'transparent',
              color:        live ? 'var(--text)' : 'var(--text-3)',
              borderColor:  live ? 'transparent' : 'var(--border)',
            }}
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
                style={active ? { ...chipBase, background: 'var(--surface-3)', color: 'var(--text)', borderColor: 'transparent' } : chipBase}
              >
                {c}
              </button>
            )
          })}
        </div>
      </div>

      {/* Log body */}
      <div
        ref={bodyRef}
        className="flex-1 overflow-auto"
        onScroll={handleScroll}
        style={{ background: 'var(--bg)' }}
      >
        {isLoading ? (
          <p className="font-mono text-xs p-4" style={{ color: 'var(--text-3)' }}>Loading…</p>
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
              <LogLine key={entry.id} entry={entry} />
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
