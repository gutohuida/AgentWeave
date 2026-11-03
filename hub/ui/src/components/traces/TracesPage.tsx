import * as React from 'react'
import { format } from 'date-fns'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import { useTraces, type TraceSummary } from '@/api/traces'
import { Badge } from '@/components/common/Badge'
import { LoadingThread } from '@/components/common/LoadingThread'
import { TraceDrawerPanel } from '@/components/traces/TraceDrawer'
import { formatDuration } from '@/components/traces/traceModel'
import {
  EMPTY_FILTER,
  INTERNAL_KINDS,
  RANGES,
  costOf,
  durationMs,
  filtersToQuery,
  narrowedBy,
  subjectOf,
  type InternalKind,
  type TracesFilter,
} from '@/components/traces/tracesModel'
import { Button } from '@/components/ui/button'
import { hubDate } from '@/lib/hubTime'
import '@/styles/traces.css'

/** A cost small enough to round to $0.00 still shows its digits: it was measured, it is not zero. */
function money(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`
}

function Cost({ trace }: { trace: TraceSummary }) {
  const cost = costOf(trace)
  if (cost.kind === 'cost') return <span data-testid="trace-cost">{money(cost.usd)}</span>
  if (cost.kind === 'unpriced') {
    return (
      <span
        data-testid="trace-cost"
        className="aw-traces-unpriced"
        title="This run finished and the Hub could not measure its cost"
      >
        unpriced
      </span>
    )
  }
  return (
    <span data-testid="trace-cost" className="aw-traces-none">
      —
    </span>
  )
}

/** Narrowing to a row's task or conversation is a control of its own; the text beside it opens the run. */
function Narrow({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      className="aw-traces-narrow"
      aria-label={label}
      title={label}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
    >
      only
    </button>
  )
}

function Subject({ trace, onNarrow }: { trace: TraceSummary; onNarrow: (patch: Partial<TracesFilter>) => void }) {
  const subject = subjectOf(trace)
  if (subject.kind === 'task') {
    const name = subject.ref ?? subject.title ?? 'this task'
    return (
      <span className="aw-traces-subject" data-testid="trace-subject">
        <span className="aw-traces-subject-text">
          {subject.ref ? <b>{subject.ref}</b> : null} {subject.title}
        </span>
        <Narrow label={`Only runs of ${name}`} onClick={() => onNarrow({ task: trace.task_id ?? '' })} />
      </span>
    )
  }
  if (subject.kind === 'missing-task') {
    return (
      <span className="aw-traces-subject aw-traces-missing" data-testid="trace-subject">
        Task no longer exists
      </span>
    )
  }
  if (subject.kind === 'conversation') {
    return (
      <span className="aw-traces-subject" data-testid="trace-subject">
        <span className="aw-traces-subject-text">
          <i>Conversation turn</i> · {subject.title}
        </span>
        <Narrow
          label={`Only turns of ${subject.title}`}
          onClick={() => onNarrow({ conversation: trace.conversation_id ?? '' })}
        />
      </span>
    )
  }
  return <span className="aw-traces-subject aw-traces-none">—</span>
}

function TraceRowView({
  trace,
  onOpen,
  onNarrow,
}: {
  trace: TraceSummary
  onOpen: () => void
  onNarrow: (patch: Partial<TracesFilter>) => void
}) {
  const isRun = trace.kind === 'run'
  const duration = durationMs(trace)
  return (
    <li
      className="aw-traces-row"
      data-testid="trace-row"
      data-run-id={trace.run_id ?? ''}
      data-trace-id={trace.trace_id}
      data-error={trace.is_error ? 'true' : 'false'}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onOpen()
        }
      }}
    >
      <span className="aw-traces-when">{format(hubDate(trace.start_time), 'MMM d HH:mm:ss')}</span>
      <span className="aw-traces-agent">{isRun ? trace.agent ?? '—' : trace.name}</span>
      <span className="aw-traces-model">{isRun ? trace.model ?? '—' : null}</span>
      {isRun ? <Subject trace={trace} onNarrow={onNarrow} /> : <span className="aw-traces-subject" />}
      <span className="aw-traces-duration">{duration === null ? 'running' : formatDuration(duration)}</span>
      {isRun ? <Cost trace={trace} /> : <span />}
      <span className="aw-traces-outcome">
        {trace.is_error ? (
          <Badge variant="danger">
            {trace.run_status && trace.run_status !== 'failed' ? trace.run_status : 'error'}
          </Badge>
        ) : null}
      </span>
    </li>
  )
}

/**
 * Activity → Traces: agents' runs by default, the Hub's own traces behind a quiet "Hub internals"
 * choice; filters by agent, conversation, task, run and time range. A row opens its trace in the
 * drawer; the filters live here, so closing the drawer returns to the same list.
 */
export function TracesPage() {
  const [filter, setFilter] = React.useState<TracesFilter>(EMPTY_FILTER)
  // The moment a range is measured from is taken when the filter changes, so the query key is still.
  const [anchor, setAnchor] = React.useState(() => new Date())
  const [before, setBefore] = React.useState<string | undefined>(undefined)
  const [opened, setOpened] = React.useState<TraceSummary | null>(null)
  const { data: agents = [] } = useAgents()

  const change = (patch: Partial<TracesFilter>) => {
    setFilter((current) => ({ ...current, ...patch }))
    setAnchor(new Date())
    setBefore(undefined)
  }
  const query = React.useMemo(() => filtersToQuery(filter, anchor, before), [filter, anchor, before])
  const { data, isLoading, error } = useTraces(query)
  const traces = data?.traces ?? []
  const internal = INTERNAL_KINDS.find((k) => k.value === filter.kind)

  return (
    <div className="aw-traces" data-testid="traces-view">
      <div className="aw-traces-filters" role="group" aria-label="Trace filters">
        <select
          aria-label="Agent"
          data-testid="traces-filter-agent"
          value={filter.agent}
          onChange={(event) => change({ agent: event.target.value })}
          className="control-field"
        >
          <option value="">All agents</option>
          {agents.map((agent) => (
            <option key={agent.name} value={agent.name}>
              {agent.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Time range"
          data-testid="traces-filter-range"
          value={filter.day ? 'all' : filter.range}
          onChange={(event) => change({ range: event.target.value as TracesFilter['range'], day: '' })}
          className="control-field"
        >
          {RANGES.map((range) => (
            <option key={range.value} value={range.value}>
              {range.label}
            </option>
          ))}
        </select>
        <input
          type="date"
          aria-label="Day"
          data-testid="traces-filter-day"
          value={filter.day}
          onChange={(event) => change({ day: event.target.value })}
          className="control-field"
        />
        <input
          aria-label="Task"
          data-testid="traces-filter-task"
          placeholder="Task"
          value={filter.task}
          onChange={(event) => change({ task: event.target.value })}
          className="control-field"
        />
        <input
          aria-label="Conversation"
          data-testid="traces-filter-conversation"
          placeholder="Conversation"
          value={filter.conversation}
          onChange={(event) => change({ conversation: event.target.value })}
          className="control-field"
        />
        <input
          aria-label="Run"
          data-testid="traces-filter-run"
          placeholder="Run"
          value={filter.run}
          onChange={(event) => change({ run: event.target.value })}
          className="control-field"
        />
        {narrowedBy(filter) ? (
          <Button type="button" variant="outline" size="xs" onClick={() => change({ ...EMPTY_FILTER, kind: filter.kind })}>
            Clear filters
          </Button>
        ) : null}
        <span className="aw-traces-spacer" />
        <select
          aria-label="Hub internals"
          data-testid="traces-internals"
          value={filter.kind ?? ''}
          onChange={(event) => change({ kind: (event.target.value || null) as InternalKind | null })}
          className="control-field aw-traces-internals"
        >
          <option value="">Hub internals…</option>
          {INTERNAL_KINDS.map((kind) => (
            <option key={kind.value} value={kind.value}>
              {kind.label}
            </option>
          ))}
        </select>
      </div>

      {internal ? (
        <p className="aw-traces-internal-note" data-testid="traces-internal-note">
          Showing the Hub’s own {internal.label.toLowerCase()}, not agents’ runs.{' '}
          <button type="button" className="aw-link" onClick={() => change({ kind: null })}>
            Back to agent runs
          </button>
        </p>
      ) : null}

      {isLoading ? (
        <LoadingThread label="Loading traces" />
      ) : error ? (
        <p role="alert" className="aw-traces-error">
          {readableApiError(error, 'The traces could not be listed.')}
        </p>
      ) : traces.length === 0 ? (
        <p className="aw-traces-empty">{before ? 'No older traces.' : 'No traces match.'}</p>
      ) : (
        <>
          <p className="aw-traces-count" data-testid="traces-count" data-value={traces.length}>
            {traces.length} {internal ? 'trace' : 'run'}
            {traces.length === 1 ? '' : 's'}
            {data?.next_before ? ' on this page' : ''}
          </p>
          <ul className="aw-traces-list">
            {traces.map((trace) => (
              <TraceRowView key={trace.trace_id} trace={trace} onOpen={() => setOpened(trace)} onNarrow={change} />
            ))}
          </ul>
          <div className="aw-traces-paging">
            {before ? (
              <Button type="button" variant="outline" size="xs" onClick={() => setBefore(undefined)}>
                Newest
              </Button>
            ) : null}
            {data?.next_before ? (
              <Button type="button" variant="outline" size="xs" onClick={() => setBefore(data.next_before ?? undefined)}>
                Older
              </Button>
            ) : null}
          </div>
        </>
      )}

      <TraceDrawerPanel
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null)
        }}
        runId={opened?.run_id ?? undefined}
        traceId={opened && !opened.run_id ? opened.trace_id : undefined}
      />
    </div>
  )
}
