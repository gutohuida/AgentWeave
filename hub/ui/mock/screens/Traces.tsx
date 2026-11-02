import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { TraceDetail, TraceKind } from '@/api/traces'
import { TraceDrawer } from '@/components/traces/TraceDrawer'
import { TracesPage } from '@/components/traces/TracesPage'
import { DEFAULT_FILTERS, groupRows, matches, totals, type TraceFilters, type TraceGrouping, type TraceRow } from '@/components/traces/tracesModel'
import { Segmented } from '@/components/ui/segmented'
import runsJson from '../fixtures/traces_runs.json'
import hubJson from '../fixtures/traces_hub.json'
import detailsJson from '../fixtures/traces_details.json'
import { PROJECT_ID } from '../fixtures'
import { useTracesPlacement } from '../tracesMock'
import type { ScreenProps } from '../routes'
import '@/styles/activity.css'

/** Recorded from the operator's Hub on 2026-11-02 with `py -3.11 mock/record_traces.py`, read-only:
 *  every run trace of the AgentWeave project (1,170), the newest 200 of each kind of the Hub's own
 *  traces with each kind's total, and 22 whole run traces (the newest five and every error). */
type RunJson = Omit<TraceRow, 'kind' | 'name'>
type HubJson = Record<string, { total: number; traces: Array<Pick<TraceRow, 'trace_id' | 'name' | 'kind' | 'agent' | 'status' | 'status_message' | 'start_time' | 'end_time'>> }>

const hub = hubJson as unknown as HubJson
const details = detailsJson as unknown as Record<string, TraceDetail>

const EMPTY: Omit<TraceRow, 'trace_id' | 'kind' | 'start_time' | 'status'> = {
  run_id: null,
  name: null,
  agent: null,
  model: null,
  task_id: null,
  task_ref: null,
  task_title: null,
  conversation_id: null,
  conversation_title: null,
  run_status: null,
  status_message: null,
  end_time: null,
  ended: true,
  cost_usd_micros: null,
  input_tokens: null,
  output_tokens: null,
  cache_read_tokens: null,
  cache_write_tokens: null,
  model_calls: 0,
  tool_calls: 0,
  tool_errors: 0,
  wait_seconds: 0,
  span_count: 1,
}

const ROWS: TraceRow[] = [
  ...(runsJson as unknown as RunJson[]).map((r) => ({ ...r, kind: 'run' as const, name: null })),
  ...Object.values(hub).flatMap((k) => k.traces.map((t) => ({ ...EMPTY, ...t }))),
]

/** The operator's agents and their colours on that Hub. */
const AGENT_COLORS: Record<string, number> = { Architect: 0, Developer: 1, QA: 2, mender: 3, DeveloperOpus: 4, QA2: 5, DeveloperOpus2: 6 }
const AGENTS = Object.keys(AGENT_COLORS)

/** The mock's clock: five minutes after the newest recorded run. */
const NOW = new Date(Math.max(...ROWS.filter((r) => r.kind === 'run').map((r) => new Date(r.start_time).getTime())) + 5 * 60_000)

const PAGE = 50

export default function Traces({ go }: ScreenProps) {
  const placement = useTracesPlacement()
  const client = useQueryClient()
  const [filters, setFilters] = React.useState<TraceFilters>(DEFAULT_FILTERS)
  const [grouping, setGrouping] = React.useState<TraceGrouping>('none')
  const [shown, setShown] = React.useState(PAGE)
  const [open, setOpen] = React.useState<TraceRow | null>(null)
  const triggerRef = React.useRef<HTMLButtonElement | null>(null)

  // The drawer reads through the app's own hook; the recorded whole traces answer it from the cache.
  React.useMemo(() => {
    for (const [runId, detail] of Object.entries(details)) client.setQueryData(['project', PROJECT_ID, 'traces', 'by-run', runId, 0], detail)
  }, [client])

  const onFilters = (next: TraceFilters) => {
    setFilters(next)
    setShown(PAGE)
  }

  const filtered = React.useMemo(() => ROWS.filter((r) => matches(r, filters, NOW)), [filters])
  const sum = React.useMemo(() => totals(filtered), [filtered])
  const groups = React.useMemo(() => (grouping === 'none' ? [] : groupRows(filtered, grouping)), [filtered, grouping])
  const kindCounts = React.useMemo(() => {
    const counts: Partial<Record<TraceKind, number>> = {}
    const unfiltered = !filters.agent && filters.range === 'all' && !filters.task && !filters.conversation && !filters.run
    for (const kind of ['run', 'worker', 'request', 'work', 'event'] as TraceKind[]) {
      // mock state: the Hub's own kinds are a sample of 200; unfiltered, the switch shows the real total.
      counts[kind] = kind !== 'run' && unfiltered ? hub[kind]?.total : ROWS.filter((r) => matches(r, { ...filters, kind }, NOW)).length
    }
    return counts
  }, [filters])

  const page = (
    <>
      {filters.kind !== 'run' ? (
        <p className="mock-note" style={{ maxWidth: 1100, margin: '12px auto 0', padding: '0 24px', fontSize: 12, color: 'var(--text-3)' }}>
          Mock: the Hub’s own traces are a sample, the newest 200 of {hub[filters.kind]?.total.toLocaleString()}; the app totals all of them.
        </p>
      ) : null}
      <TracesPage
        filters={filters}
        onFilters={onFilters}
        grouping={grouping}
        onGrouping={setGrouping}
        totals={sum}
        kindCounts={kindCounts}
        rows={filtered.slice(0, shown)}
        hasMore={filtered.length > shown}
        onMore={() => setShown((n) => n + PAGE)}
        groups={groups}
        agents={AGENTS}
        colorIndexOf={(a) => AGENT_COLORS[a]}
        onOpen={(row) => {
          triggerRef.current = document.activeElement as HTMLButtonElement
          setOpen(row)
        }}
        now={NOW}
      />
      <TraceDrawer
        open={open !== null}
        onOpenChange={(o) => (o ? undefined : setOpen(null))}
        runId={open?.run_id ?? undefined}
        traceId={open?.run_id ? undefined : open?.trace_id}
        triggerRef={triggerRef}
        emptyDescription="Mock: whole traces are recorded for 22 runs only, the newest five and every error. In the app every listed trace opens."
      />
    </>
  )

  if (placement === 'tab') return page
  return (
    <div className="aw-activity-page">
      <div className="aw-activity-head">
        <Segmented
          label="Activity view"
          value={'traces' as string}
          onChange={(v) => (v === 'traces' ? undefined : go({ kind: 'tab', tab: 'activity' }))}
          options={[
            { value: 'ledger', label: 'Ledger' },
            { value: 'activity', label: 'Activity' },
            { value: 'logs', label: 'Logs' },
            { value: 'traces', label: 'Traces' },
          ]}
        />
      </div>
      {page}
    </div>
  )
}
