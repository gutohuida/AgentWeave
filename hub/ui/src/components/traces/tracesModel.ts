import type { TraceFilters, TraceGroup, TraceGrouping, TraceOperation, TraceSummary, TraceTotals } from '@/api/traces'
import { hubDate } from '@/lib/hubTime'

/** What the view narrows by. `kind` is the Hub-internals choice; null is agents' runs. */
export interface TracesFilter {
  agent: string
  conversation: string
  task: string
  run: string
  range: TracesRange
  /** A calendar day (YYYY-MM-DD, the operator's own), which stands in for the range when set. */
  day: string
  kind: InternalKind | null
}

export type TracesRange = 'all' | '1h' | '24h' | '7d' | '30d'

export const EMPTY_FILTER: TracesFilter = {
  agent: '',
  conversation: '',
  task: '',
  run: '',
  range: 'all',
  day: '',
  kind: null,
}

export const RANGES: ReadonlyArray<{ value: TracesRange; label: string; ms: number }> = [
  { value: 'all', label: 'Any time', ms: 0 },
  { value: '1h', label: 'Last hour', ms: 60 * 60 * 1000 },
  { value: '24h', label: 'Last 24 hours', ms: 24 * 60 * 60 * 1000 },
  { value: '7d', label: 'Last 7 days', ms: 7 * 24 * 60 * 60 * 1000 },
  { value: '30d', label: 'Last 30 days', ms: 30 * 24 * 60 * 60 * 1000 },
]

/** The Hub's own kinds, offered only inside the Hub internals choice. */
export type InternalKind = 'worker' | 'request' | 'work' | 'event'

export const INTERNAL_KINDS: ReadonlyArray<{ value: InternalKind; label: string; operation: TraceOperation }> = [
  { value: 'worker', label: 'Worker calls', operation: 'chat' },
  { value: 'request', label: 'Requests', operation: 'aw.request' },
  { value: 'work', label: 'Background work', operation: 'aw.work' },
  { value: 'event', label: 'Events', operation: 'aw.event' },
]

/** The route's query for a filter. `now` is read when the range is chosen, not on every render,
 *  so the query key stays still while the list is on screen. */
export function filtersToQuery(filter: TracesFilter, now: Date, before?: string): TraceFilters {
  const query: TraceFilters = {}
  const internal = INTERNAL_KINDS.find((k) => k.value === filter.kind)
  query.operation = internal ? internal.operation : 'invoke_agent'
  if (filter.agent) query.agent = filter.agent
  if (filter.conversation.trim()) query.conversation_id = filter.conversation.trim()
  if (filter.task.trim()) query.task_id = filter.task.trim()
  if (filter.run.trim()) query.run_id = filter.run.trim()
  if (filter.day) {
    const [y, m, d] = filter.day.split('-').map(Number)
    if (y && m && d) {
      query.since = new Date(y, m - 1, d).toISOString()
      query.until = new Date(y, m - 1, d + 1).toISOString()
    }
  } else {
    const range = RANGES.find((r) => r.value === filter.range)
    if (range && range.ms) query.since = new Date(now.getTime() - range.ms).toISOString()
  }
  if (before) query.before = before
  return query
}

export function narrowedBy(filter: TracesFilter): boolean {
  return !!(
    filter.agent ||
    filter.conversation.trim() ||
    filter.task.trim() ||
    filter.run.trim() ||
    filter.day ||
    filter.range !== 'all'
  )
}

/** What a row says about the work: a task (reference and title), a task that is gone, or the
 *  conversation it was a turn of. Never a raw id. */
export type TraceSubject =
  | { kind: 'task'; ref: string | null; title: string | null }
  | { kind: 'missing-task' }
  | { kind: 'conversation'; title: string }
  | { kind: 'none' }

export function subjectOf(trace: TraceSummary): TraceSubject {
  if (trace.task_missing) return { kind: 'missing-task' }
  if (trace.task_id) {
    if (trace.task_ref || trace.task_title) {
      return { kind: 'task', ref: trace.task_ref ?? null, title: trace.task_title ?? null }
    }
    return { kind: 'missing-task' }
  }
  if (trace.conversation_id) {
    return { kind: 'conversation', title: trace.conversation_title?.trim() || 'New conversation' }
  }
  return { kind: 'none' }
}

export function durationMs(trace: TraceSummary): number | null {
  if (!trace.end_time) return null
  return Math.max(0, hubDate(trace.end_time).getTime() - hubDate(trace.start_time).getTime())
}

/** A run's cost as its row says it: a figure, "unpriced" (finished, not measured), or nothing
 *  yet (still running). Never $0.00 for a cost that was not measured. */
export type CostCell = { kind: 'cost'; usd: number } | { kind: 'unpriced' } | { kind: 'none' }

export function costOf(trace: TraceSummary): CostCell {
  if (trace.cost_state === 'measured' && trace.cost_usd != null) return { kind: 'cost', usd: trace.cost_usd }
  if (trace.cost_state === 'unpriced') return { kind: 'unpriced' }
  return { kind: 'none' }
}

/** The grouping switch, in the order it is offered. `none` lists the runs ungrouped. */
export const GROUPINGS: ReadonlyArray<{ value: TraceGrouping | 'none'; label: string }> = [
  { value: 'none', label: 'None' },
  { value: 'agent', label: 'Agent' },
  { value: 'model', label: 'Model' },
  { value: 'task', label: 'Task' },
  { value: 'conversation', label: 'Conversation' },
  { value: 'kind', label: 'Kind' },
  { value: 'day', label: 'Day' },
]

/** The filter that narrows the view to one group, where the list can filter by what it groups. */
export function groupNarrow(grouping: TraceGrouping, group: TraceGroup): Partial<TracesFilter> | null {
  if (!group.key || group.missing) return null
  if (grouping === 'agent') return { agent: group.key }
  if (grouping === 'task') return { task: group.key }
  if (grouping === 'conversation') return { conversation: group.key }
  if (grouping === 'day') return { day: group.key, range: 'all' }
  return null
}

/** A total's cost as it reads: a figure over the measured runs, "unpriced" when every finished
 *  run in it went unmeasured, or nothing (still running, or the Hub's own work). Never $0.00 for
 *  a cost that was not measured. */
export function totalCostOf(totals: TraceTotals): CostCell {
  if (totals.cost_usd_micros !== null) return { kind: 'cost', usd: totals.cost_usd_micros / 1_000_000 }
  if (totals.unpriced) return { kind: 'unpriced' }
  return { kind: 'none' }
}

/** Why the errors count, in the operator's words: "1 failed · 2 stopped · 1 ended in error". */
export function errorBreakdown(totals: TraceTotals): string {
  const k = totals.error_kinds
  return [
    k.failed ? `${k.failed} failed` : null,
    k.stopped ? `${k.stopped} stopped` : null,
    k.trace_error ? `${k.trace_error} ended in error` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}
