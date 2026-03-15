import { useEffect, useMemo, useRef, useState } from 'react'
import { Search, RefreshCw } from 'lucide-react'
import { useLogs } from '@/api/logs'
import { LogLine } from './LogLine'
import { useQueryClient } from '@tanstack/react-query'

const SEVERITIES = ['all', 'error', 'warn', 'info', 'debug'] as const
type Severity = (typeof SEVERITIES)[number]

const SEVERITY_PILL_ACTIVE: Record<Severity, string> = {
  all:   'bg-white/10 text-white ring-1 ring-white/20',
  error: 'bg-red-500/15 text-red-400 ring-1 ring-red-500/20',
  warn:  'bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/20',
  info:  'bg-primary/15 text-primary ring-1 ring-primary/20',
  debug: 'bg-white/[0.06] text-white/40 ring-1 ring-white/10',
}
const PILL_INACTIVE = 'text-white/30 hover:text-white/60 hover:bg-white/[0.05]'

const KNOWN_AGENTS = ['', 'claude', 'kimi', 'system']

export function LogsView() {
  const [search, setSearch] = useState('')
  const [severity, setSeverity] = useState<Severity>('all')
  const [agentFilter, setAgentFilter] = useState('')
  const [live, setLive] = useState(true)
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  const { data: entries = [], isLoading, dataUpdatedAt } = useLogs({
    agent: agentFilter || undefined,
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
    <div className="flex flex-col h-full text-white/80">
      {/* ── Toolbar ── */}
      <div className="flex flex-col gap-2 px-3 py-2.5 shrink-0"
           style={{ borderBottom: '1px solid rgba(255,255,255,0.07)', background: 'rgba(0,0,0,0.20)' }}>
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/25 pointer-events-none" />
            <input
              type="text"
              placeholder="Search event type, agent, data…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-8 rounded-lg pl-8 pr-3 text-xs text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)' }}
            />
          </div>

          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="h-8 rounded-lg px-2 text-xs text-white/60 focus:outline-none focus:ring-1 focus:ring-primary"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)' }}
          >
            <option value="">All agents</option>
            {KNOWN_AGENTS.filter(Boolean).map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          <button
            onClick={refresh}
            className="h-8 w-8 flex items-center justify-center rounded-lg text-white/40 hover:text-white/80 transition-colors"
            style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)' }}
            title="Refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => setLive(!live)}
            className={`flex items-center gap-1.5 h-8 rounded-lg px-3 text-xs font-medium transition-colors ${
              live
                ? 'bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30'
                : 'text-white/40 hover:text-white/70'
            }`}
            style={live ? {} : { background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.09)' }}
          >
            {live && <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />}
            {live ? 'Live' : 'Paused'}
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          {SEVERITIES.map((s) => (
            <button
              key={s}
              onClick={() => setSeverity(s)}
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize transition-colors ${
                severity === s ? SEVERITY_PILL_ACTIVE[s] : PILL_INACTIVE
              }`}
            >
              {s}
            </button>
          ))}
          <span className="ml-auto text-[11px] text-white/20 tabular-nums font-mono">
            {filtered.length.toLocaleString()} entr{filtered.length === 1 ? 'y' : 'ies'}
            {search ? ` (filtered)` : ''}
            {live && <span className="ml-2">· {lastUpdate}</span>}
          </span>
        </div>
      </div>

      {/* ── Log body ── */}
      <div ref={bodyRef} className="flex-1 overflow-auto" onScroll={handleScroll}
           style={{ background: 'rgba(0,0,0,0.30)' }}>
        {isLoading ? (
          <p className="font-mono text-xs text-white/20 p-4">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="font-mono text-xs text-white/20 p-4">
            {search || severity !== 'all' || agentFilter
              ? 'No entries match the current filters.'
              : 'No log entries yet. Trigger some activity to see entries here.'}
          </p>
        ) : (
          <>
            <div className="sticky top-0 z-10 flex items-center gap-2 px-2 py-1 font-mono text-[10px] text-white/20 select-none"
                 style={{ background: 'rgba(0,0,0,0.40)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
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

      {/* ── Scroll nudge ── */}
      {live && !autoScroll && (
        <div className="shrink-0 flex justify-center py-1.5" style={{ background: 'rgba(0,0,0,0.30)', borderTop: '1px solid rgba(255,255,255,0.07)' }}>
          <button
            onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }}
            className="text-xs text-primary hover:opacity-80"
          >
            ↓ Jump to latest
          </button>
        </div>
      )}
    </div>
  )
}
