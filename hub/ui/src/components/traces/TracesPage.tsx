import * as React from 'react'
import { format } from 'date-fns'
import { readableApiError } from '@/api/client'
import { useAgents } from '@/api/agents'
import {
  useTraceTotals,
  useTraces,
  type TraceGroup,
  type TraceGrouping,
  type TraceSummary,
  type TraceTotals,
} from '@/api/traces'
import { Badge } from '@/components/common/Badge'
import { LoadingThread } from '@/components/common/LoadingThread'
import { TraceDrawerPanel } from '@/components/traces/TraceDrawer'
import { formatDuration } from '@/components/traces/traceModel'
import {
  EMPTY_FILTER,
  GROUPINGS,
  INTERNAL_KINDS,
  RANGES,
  costOf,
  durationMs,
  errorBreakdown,
  filtersToQuery,
  groupNarrow,
  narrowedBy,
  subjectOf,
  totalCostOf,
  type CostCell,
  type InternalKind,
  type TracesFilter,
} from '@/components/traces/tracesModel'
import { Button } from '@/components/ui/button'
import type { TracesRequest } from '@/store/tracesRequestStore'
import { Segmented } from '@/components/ui/segmented'
import { formatCount, formatTokens, formatTokensExact } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'
import '@/styles/traces.css'

/** A cost small enough to round to $0.00 still shows its digits: it was measured, it is not zero. */
function money(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`
}

function Cost({ trace }: { trace: TraceSummary }) {
  return <CostText cost={costOf(trace)} />
}

function CostText({ cost, testId = 'trace-cost' }: { cost: CostCell; testId?: string }) {
  if (cost.kind === 'cost') return <span data-testid={testId}>{money(cost.usd)}</span>
  if (cost.kind === 'unpriced') {
    return (
      <span
        data-testid={testId}
        className="aw-traces-unpriced"
        title="This run finished and the Hub could not measure its cost"
      >
        unpriced
      </span>
    )
  }
  return (
    <span data-testid={testId} className="aw-traces-none">
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

/** Cost, duration and errors first (FR-6), over everything the filter matches (FR-8); tokens,
 *  calls and waiting on one quieter line after them (FR-7). */
function Headline({ totals, isRuns }: { totals: TraceTotals; isRuns: boolean }) {
  const cost = totalCostOf(totals)
  const why = errorBreakdown(totals)
  return (
    <section className="aw-traces-stats" aria-label="Totals" data-testid="traces-totals">
      <div className="aw-traces-tile" data-testid="traces-stat-cost">
        <span className="aw-traces-tile-label">Cost</span>
        <strong>{isRuns ? <CostText cost={cost} testId="traces-total-cost" /> : '—'}</strong>
        <small data-testid="traces-unpriced-note">
          {!isRuns
            ? 'The Hub’s own work is not billed'
            : totals.unpriced
              ? `${plural(totals.unpriced, 'unpriced run')} left out`
              : totals.priced
                ? 'Every finished run priced'
                : 'No finished run yet'}
        </small>
      </div>
      <div className="aw-traces-tile" data-testid="traces-stat-duration">
        <span className="aw-traces-tile-label">Duration</span>
        <strong data-testid="traces-total-duration">{formatDuration(totals.duration_seconds * 1000)}</strong>
        <small data-testid="traces-average-duration">
          {totals.duration_avg_seconds === null
            ? 'Nothing has finished'
            : `${formatDuration(totals.duration_avg_seconds * 1000)} on average`}
          {totals.running ? ` · ${totals.running} still running` : ''}
        </small>
      </div>
      <div className="aw-traces-tile" data-testid="traces-stat-errors" data-bad={totals.errors ? 'true' : undefined}>
        <span className="aw-traces-tile-label">Errors</span>
        <strong data-testid="traces-total-errors">{formatCount(totals.errors)}</strong>
        <small>{why || `None of ${plural(totals.count, isRuns ? 'run' : 'trace')}`}</small>
      </div>
      {isRuns ? (
        <div className="aw-traces-secondary" data-testid="traces-secondary">
          <span
            data-testid="traces-tokens"
            title={
              totals.tokens
                ? `${formatTokensExact(totals.tokens.input)} in · ${formatTokensExact(totals.tokens.output)} out · ${formatTokensExact(totals.tokens.cache_read)} read from cache · ${formatTokensExact(totals.tokens.cache_write)} written to cache`
                : undefined
            }
          >
            {totals.tokens ? formatTokens(totals.tokens.input + totals.tokens.output) : 'No tokens recorded'}
          </span>
          <span data-testid="traces-model-calls">{plural(totals.model_calls, 'model call')}</span>
          <span data-testid="traces-tool-calls">{plural(totals.tool_calls, 'tool call')}</span>
          <span data-testid="traces-waiting">
            {totals.wait_seconds ? `${formatDuration(totals.wait_seconds * 1000)} waiting on you` : 'No waiting on you'}
          </span>
        </div>
      ) : null}
    </section>
  )
}

/** One row per group: its count, then the same three statistics, with a bar for its cost share. */
function Groups({
  grouping,
  groups,
  overall,
  isRuns,
  onNarrow,
}: {
  grouping: TraceGrouping
  groups: TraceGroup[]
  overall: TraceTotals
  isRuns: boolean
  onNarrow: (patch: Partial<TracesFilter>) => void
}) {
  const label = GROUPINGS.find((g) => g.value === grouping)?.label ?? ''
  return (
    <div className="aw-traces-groups" data-testid="traces-groups" data-grouping={grouping}>
      <div className="aw-traces-group aw-traces-group-head" aria-hidden="true">
        <span>{label}</span>
        <span>{isRuns ? 'Runs' : 'Traces'}</span>
        <span>Cost</span>
        <span>Took</span>
        <span>Errors</span>
        <span />
      </div>
      {groups.map((group) => {
        const t = group.totals
        const cost = totalCostOf(t)
        const share =
          isRuns && overall.cost_usd_micros && t.cost_usd_micros !== null ? t.cost_usd_micros / overall.cost_usd_micros : null
        const narrow = groupNarrow(grouping, group)
        return (
          <div className="aw-traces-group" data-testid="traces-group" data-key={group.key} key={group.key}>
            <span className={group.missing ? 'aw-traces-group-name aw-traces-missing' : 'aw-traces-group-name'}>
              <span className="aw-traces-subject-text">{group.label}</span>
              {group.detail ? <small>{group.detail}</small> : null}
            </span>
            <span className="aw-traces-group-num" data-testid="traces-group-count">
              {formatCount(t.count)}
            </span>
            <span className="aw-traces-group-num">
              {isRuns ? <CostText cost={cost} testId="traces-group-cost" /> : <span data-testid="traces-group-cost">—</span>}
              {isRuns && t.unpriced && cost.kind === 'cost' ? (
                <small data-testid="traces-group-unpriced">+{t.unpriced} unpriced</small>
              ) : null}
              {share !== null ? (
                <span className="aw-traces-share" style={{ ['--share' as string]: `${Math.max(2, share * 100)}%` }} />
              ) : null}
            </span>
            <span className="aw-traces-group-num" data-testid="traces-group-duration">
              {formatDuration(t.duration_seconds * 1000)}
              <small>{t.duration_avg_seconds === null ? '' : `${formatDuration(t.duration_avg_seconds * 1000)} avg`}</small>
            </span>
            <span className="aw-traces-group-num" data-testid="traces-group-errors" data-bad={t.errors ? 'true' : undefined}>
              {t.errors ? plural(t.errors, 'error') : '—'}
            </span>
            <span>
              {narrow ? (
                <button type="button" className="aw-link" onClick={() => onNarrow(narrow)}>
                  Only this
                </button>
              ) : null}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/**
 * Activity → Traces: agents' runs by default, the Hub's own traces behind a quiet "Hub internals"
 * choice; filters by agent, conversation, task, run and time range. A row opens its trace in the
 * drawer; the filters live here, so closing the drawer returns to the same list.
 */
export function TracesPage({ request = null }: { request?: TracesRequest | null }) {
  const [filter, setFilter] = React.useState<TracesFilter>(() => ({
    ...EMPTY_FILTER,
    build: request?.build ?? '',
    task: request?.task ?? '',
    agent: request?.agent ?? '',
  }))
  // The moment a range is measured from is taken when the filter changes, so the query key is still.
  const [anchor, setAnchor] = React.useState(() => new Date())
  const [before, setBefore] = React.useState<string | undefined>(undefined)
  // Set when the operator lets go of the runs a count asked for (its `since` is not a filter field).
  const [released, setReleased] = React.useState(false)
  const [opened, setOpened] = React.useState<TraceSummary | null>(null)
  const [grouping, setGrouping] = React.useState<TraceGrouping | 'none'>('none')
  const { data: agents = [], error: agentsError } = useAgents()

  const change = (patch: Partial<TracesFilter>) => {
    setFilter((current) => ({ ...current, ...patch }))
    setAnchor(new Date())
    setBefore(undefined)
  }
  const query = React.useMemo(() => {
    const q = filtersToQuery(filter, anchor, before)
    // A run count's "since" is a bound of its own; the range selector may narrow it further, never widen it.
    if (!released && request?.since && (!q.since || q.since < request.since)) q.since = request.since
    return q
  }, [filter, anchor, before, request, released])
  const { data, isLoading, error } = useTraces(query)
  // The statistics are the Hub's, over every trace the filter matches, not this page (FR-8).
  const totalsQuery = useTraceTotals(query, grouping === 'none' ? null : grouping)
  const overall = totalsQuery.data?.totals
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

      {agentsError ? (
        <p role="alert" className="aw-traces-error">
          {readableApiError(agentsError, 'The agents could not be listed, so the agent filter has no choices.')}
        </p>
      ) : null}

      {request?.label && !released ? (
        <p className="aw-traces-internal-note" data-testid="traces-request-note">
          Showing the runs of {request.label}.{' '}
          <button type="button" className="aw-link" onClick={() => {
              setReleased(true)
              change({ build: '', task: '', agent: '' })
            }}>
            Show all runs
          </button>
        </p>
      ) : null}

      {internal ? (
        <p className="aw-traces-internal-note" data-testid="traces-internal-note">
          Showing the Hub’s own {internal.label.toLowerCase()}, not agents’ runs.{' '}
          <button type="button" className="aw-link" onClick={() => change({ kind: null })}>
            Back to agent runs
          </button>
        </p>
      ) : null}

      {totalsQuery.error ? (
        <p role="alert" className="aw-traces-error">
          {readableApiError(totalsQuery.error, 'The statistics could not be computed.')}
        </p>
      ) : overall ? (
        <Headline totals={overall} isRuns={!internal} />
      ) : null}

      <div className="aw-traces-groupbar">
        <span className="aw-traces-groupbar-label">Group by</span>
        <Segmented label="Group by" size="xs" value={grouping} onChange={setGrouping} options={GROUPINGS} />
        {overall ? (
          <span className="aw-traces-groupbar-count" data-testid="traces-total-count" data-value={overall.count}>
            {plural(overall.count, internal ? 'trace' : 'run')}
          </span>
        ) : null}
      </div>

      {grouping !== 'none' && overall && totalsQuery.data?.groups ? (
        <Groups
          grouping={grouping}
          groups={totalsQuery.data.groups}
          overall={overall}
          isRuns={!internal}
          onNarrow={change}
        />
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
            {data?.next_before || before
              ? `${plural(traces.length, internal ? 'trace' : 'run')} on this page${overall ? ` of ${formatCount(overall.count)}` : ''}`
              : plural(traces.length, internal ? 'trace' : 'run')}
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
