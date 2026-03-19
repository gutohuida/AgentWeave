import { useEffect, useMemo, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { useLogs } from '@/api/logs'
import { LogLine } from './LogLine'
import { useQueryClient } from '@tanstack/react-query'

const SEVERITIES = ['all', 'error', 'warn', 'info', 'debug'] as const
type Severity = (typeof SEVERITIES)[number]

const SEVERITY_ACTIVE_STYLE: Record<Severity, { bg: string; color: string }> = {
  all:   { bg: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  error: { bg: 'var(--error-cont)',      color: 'var(--on-error-cont)' },
  warn:  { bg: 'var(--t-cont)',          color: 'var(--on-t-cont)' },
  info:  { bg: 'var(--p-cont)',          color: 'var(--on-p-cont)' },
  debug: { bg: 'var(--surface-highest)', color: 'var(--on-sv)' },
}

const KNOWN_AGENTS = ['', 'claude', 'kimi', 'system']

export function LogsView() {
  const [search,      setSearch]      = useState('')
  const [severity,    setSeverity]    = useState<Severity>('all')
  const [agentFilter, setAgentFilter] = useState('')
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

  const filtered = useMemo(() => {
    if (!search.trim()) return entries
    const q = search.toLowerCase()
    return entries.filter((e) => {
      if (e.event_type.toLowerCase().includes(q)) return true
      if ((e.agent ?? '').toLowerCase().includes(q)) return true
      if (JSON.stringify(e.data ?? {}).toLowerCase().includes(q)) return true
      return false
    })
  }, [entries, search])

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

  return (
    <div className="flex flex-col h-full" style={{ color: 'var(--foreground)' }}>
      {/* Toolbar */}
      <div
        className="flex flex-col gap-2 px-3 py-2.5 shrink-0 border-b"
        style={{ background: 'var(--surface-low)', borderColor: 'var(--outline-variant)' }}
      >
        <div className="flex items-center gap-2">
          {/* Search */}
          <div
            className="relative flex-1 flex items-center"
            style={{
              background: 'var(--surface-highest)',
              borderRadius: 4,
              border: '1px solid var(--outline)',
            }}
          >
            <Icon name="search" size={16} className="absolute left-2.5 pointer-events-none" style={{ color: 'var(--on-sv)' }} />
            <input
              type="text"
              placeholder="Search event type, agent, data…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-8 pl-9 pr-3 m3-body-small focus:outline-none bg-transparent"
              style={{ color: 'var(--foreground)' }}
            />
          </div>

          {/* Agent filter */}
          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="h-8 px-2 m3-body-small focus:outline-none rounded"
            style={{
              background: 'var(--surface-highest)',
              border: '1px solid var(--outline)',
              color: 'var(--foreground)',
              borderRadius: 4,
            }}
          >
            <option value="">All agents</option>
            {KNOWN_AGENTS.filter(Boolean).map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          {/* Refresh */}
          <button
            onClick={refresh}
            className="m3-icon-btn"
            style={{ width: 32, height: 32, border: '1px solid var(--outline-variant)', borderRadius: 8 }}
            title="Refresh"
          >
            <Icon name="refresh" size={16} />
          </button>

          {/* Live toggle */}
          <button
            onClick={() => setLive(!live)}
            className="flex items-center gap-1.5 h-8 rounded-lg px-3 m3-label-medium transition-colors border"
            style={{
              background:   live ? 'var(--p-cont)' : 'transparent',
              color:        live ? 'var(--on-p-cont)' : 'var(--on-sv)',
              borderColor:  live ? 'transparent' : 'var(--outline-variant)',
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
                className={`m3-chip-filter capitalize${active ? ' active' : ''}`}
                style={active ? { background: style!.bg, color: style!.color, borderColor: 'transparent' } : undefined}
              >
                {s}
              </button>
            )
          })}
          <span className="ml-auto m3-label-small tabular-nums font-mono" style={{ color: 'var(--on-sv)', opacity: 0.7 }}>
            {filtered.length.toLocaleString()} entr{filtered.length === 1 ? 'y' : 'ies'}
            {search ? ' (filtered)' : ''}
            {live && <span className="ml-2">· {lastUpdate}</span>}
          </span>
        </div>
      </div>

      {/* Log body */}
      <div
        ref={bodyRef}
        className="flex-1 overflow-auto"
        onScroll={handleScroll}
        style={{ background: 'var(--background)' }}
      >
        {isLoading ? (
          <p className="font-mono m3-body-small p-4" style={{ color: 'var(--on-sv)' }}>Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="font-mono m3-body-small p-4" style={{ color: 'var(--on-sv)' }}>
            {search || severity !== 'all' || agentFilter
              ? 'No entries match the current filters.'
              : 'No log entries yet. Trigger some activity to see entries here.'}
          </p>
        ) : (
          <>
            {/* Sticky column header */}
            <div
              className="sticky top-0 z-10 flex items-center gap-2 px-2 py-1 font-mono m3-label-small select-none border-b"
              style={{ background: 'var(--surface-high)', borderColor: 'var(--outline-variant)', color: 'var(--on-sv)' }}
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
          style={{ borderColor: 'var(--outline-variant)' }}
        >
          <button
            onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }}
            className="m3-label-medium flex items-center gap-1"
            style={{ color: 'var(--primary)' }}
          >
            <Icon name="arrow_downward" size={14} />
            Jump to latest
          </button>
        </div>
      )}
    </div>
  )
}
