import type { SpanStatus, TraceKind } from '@/api/traces'
import { formatDay } from '@/lib/format'
import { hubDate } from '@/lib/hubTime'

/**
 * The traces view's model (a-traces-view-with-filters-grouping-and-stats): one listed trace, the
 * filters, the error rule, totals and grouping, as pure functions.
 *
 * `TraceRow` is the shape the view's list is proposed to carry. Today's list route
 * (`TraceSummary`) has no model, cost, tokens or call counts; FR-3/FR-4 add them. The Hub computes
 * totals and groups over everything the filter matches (FR-8); the mock computes them here from a
 * recording of every run, which is the same answer.
 */
export interface TraceRow {
  trace_id: string
  run_id: string | null
  kind: TraceKind
  /** A Hub trace's own name ("GET /api/v1/…", "loop_tick"); null on a run. */
  name: string | null
  agent: string | null
  model: string | null
  task_id: string | null
  /** The task's short reference ("SHR-1") and title, when the run worked one. */
  task_ref: string | null
  task_title: string | null
  conversation_id: string | null
  conversation_title: string | null
  /** The run's outcome (`aw.run.status`): completed, failed, stopped, or null while running. */
  run_status: string | null
  status: SpanStatus
  status_message: string | null
  start_time: string
  end_time: string | null
  ended: boolean
  /** Null when the Hub could not measure it: shown as unpriced, never as $0 (FR-14). */
  cost_usd_micros: number | null
  input_tokens: number | null
  output_tokens: number | null
  cache_read_tokens: number | null
  cache_write_tokens: number | null
  model_calls: number
  tool_calls: number
  tool_errors: number
  /** Time spent waiting for a permission or an answer. */
  wait_seconds: number
  span_count: number
}

export type TimeRange = 'hour' | 'day' | 'week' | 'month' | 'all'
export type TraceGrouping = 'none' | 'agent' | 'model' | 'task' | 'conversation' | 'kind' | 'day'

/** A filter on one thing named by id, carrying the words to show for it. */
export interface NamedFilter {
  id: string
  label: string
}

export interface TraceFilters {
  kind: TraceKind
  agent: string | null
  conversation: NamedFilter | null
  task: NamedFilter | null
  run: NamedFilter | null
  range: TimeRange
}

export const DEFAULT_FILTERS: TraceFilters = { kind: 'run', agent: null, conversation: null, task: null, run: null, range: 'all' }

export const KIND_LABELS: Record<TraceKind, string> = {
  run: 'Agent runs',
  worker: 'Worker calls',
  request: 'Requests',
  work: 'Background work',
  event: 'Events',
}

export const RANGE_LABELS: Record<TimeRange, string> = {
  hour: 'Last hour',
  day: 'Last 24 hours',
  week: 'Last 7 days',
  month: 'Last 30 days',
  all: 'All time',
}

export const GROUPING_LABELS: Record<TraceGrouping, string> = {
  none: 'None',
  agent: 'Agent',
  model: 'Model',
  task: 'Task',
  conversation: 'Conversation',
  kind: 'Kind',
  day: 'Day',
}

const RANGE_MS: Record<Exclude<TimeRange, 'all'>, number> = {
  hour: 3_600_000,
  day: 86_400_000,
  week: 7 * 86_400_000,
  month: 30 * 86_400_000,
}

/** An error is a run that failed, was stopped (cancelled or interrupted), or whose trace ended in
 *  error (FR-6). A run that completed with a failed tool call inside is not: most runs have one. */
export function isError(row: TraceRow): boolean {
  return row.run_status === 'failed' || row.run_status === 'stopped' || row.status === 'error'
}

/** Why a row counts as an error, in the operator's words; null when it does not. */
export function errorLabel(row: TraceRow): string | null {
  if (row.run_status === 'failed') return 'failed'
  if (row.run_status === 'stopped') return 'stopped'
  if (row.status === 'error') return 'ended in error'
  return null
}

export function durationSeconds(row: TraceRow): number | null {
  if (!row.end_time) return null
  return Math.max(0, (hubDate(row.end_time).getTime() - hubDate(row.start_time).getTime()) / 1000)
}

export function matches(row: TraceRow, f: TraceFilters, now: Date): boolean {
  if (row.kind !== f.kind) return false
  if (f.agent && row.agent !== f.agent) return false
  if (f.conversation && row.conversation_id !== f.conversation.id) return false
  if (f.task && row.task_id !== f.task.id) return false
  if (f.run && row.run_id !== f.run.id) return false
  if (f.range !== 'all' && hubDate(row.start_time).getTime() < now.getTime() - RANGE_MS[f.range]) return false
  return true
}

export interface TraceTotals {
  count: number
  errors: number
  /** `errors`, by why each counts. */
  error_kinds: { failed: number; stopped: number; trace_error: number }
  running: number
  /** Sum over the runs whose cost was measured; null when none was. */
  cost_micros: number | null
  /** Runs left out of `cost_micros` because their cost could not be measured. */
  unpriced: number
  duration_total: number
  /** Over the traces that have ended; null when none has. */
  duration_avg: number | null
  tokens: { input: number; output: number; cache_read: number; cache_write: number } | null
  model_calls: number
  tool_calls: number
  wait_seconds: number
}

export function totals(rows: readonly TraceRow[]): TraceTotals {
  let errors = 0
  const errorKinds = { failed: 0, stopped: 0, trace_error: 0 }
  let running = 0
  let cost: number | null = null
  let unpriced = 0
  let durationTotal = 0
  let timed = 0
  let tokens: TraceTotals['tokens'] = null
  let modelCalls = 0
  let toolCalls = 0
  let wait = 0
  for (const row of rows) {
    if (isError(row)) {
      errors += 1
      if (row.run_status === 'failed') errorKinds.failed += 1
      else if (row.run_status === 'stopped') errorKinds.stopped += 1
      else errorKinds.trace_error += 1
    }
    const d = durationSeconds(row)
    if (d === null) running += 1
    else {
      durationTotal += d
      timed += 1
    }
    // A run still going has no cost yet; it is not unpriced until it ends without one.
    if (row.kind === 'run' && row.ended) {
      if (row.cost_usd_micros === null) unpriced += 1
      else cost = (cost ?? 0) + row.cost_usd_micros
    }
    if (row.input_tokens !== null || row.output_tokens !== null) {
      tokens ??= { input: 0, output: 0, cache_read: 0, cache_write: 0 }
      tokens.input += row.input_tokens ?? 0
      tokens.output += row.output_tokens ?? 0
      tokens.cache_read += row.cache_read_tokens ?? 0
      tokens.cache_write += row.cache_write_tokens ?? 0
    }
    modelCalls += row.model_calls
    toolCalls += row.tool_calls
    wait += row.wait_seconds
  }
  return {
    count: rows.length,
    errors,
    error_kinds: errorKinds,
    running,
    cost_micros: cost,
    unpriced,
    duration_total: durationTotal,
    duration_avg: timed ? durationTotal / timed : null,
    tokens,
    model_calls: modelCalls,
    tool_calls: toolCalls,
    wait_seconds: wait,
  }
}

/** What a run's task is called on screen: its reference, and its title. A task with neither no
 *  longer exists (operator, 2026-11-02): it is named as such, never by its raw id. */
export const GONE_TASK = 'A task that no longer exists'

export function taskName(row: Pick<TraceRow, 'task_ref' | 'task_title'>): { ref: string | null; title: string } {
  return { ref: row.task_ref, title: row.task_title ?? (row.task_ref ? 'Untitled task' : GONE_TASK) }
}

/** "claude-opus-5-5" → "Opus 5.5"; anything else as it came. */
export function modelLabel(model: string | null): string {
  if (!model) return 'no model'
  const m = /^claude-([a-z]+)-(\d+)-(\d+)/.exec(model)
  return m ? `${m[1]![0]!.toUpperCase()}${m[1]!.slice(1)} ${m[2]}.${m[3]}` : model
}

export interface TraceGroup {
  key: string
  label: string
  /** A second line: the task's title under its reference, a conversation's agent. */
  detail: string | null
  /** The filter that narrows the view to this group, when one exists for the grouping. */
  narrow: Partial<TraceFilters> | null
  rows: TraceRow[]
  totals: TraceTotals
}

function groupKey(row: TraceRow, grouping: TraceGrouping): { key: string; label: string; detail: string | null; narrow: Partial<TraceFilters> | null } {
  switch (grouping) {
    case 'agent':
      return { key: row.agent ?? '', label: row.agent ?? 'No agent', detail: null, narrow: row.agent ? { agent: row.agent } : null }
    case 'model':
      return { key: row.model ?? '', label: modelLabel(row.model), detail: null, narrow: null }
    case 'task':
      return row.task_id
        ? {
            key: row.task_id,
            label: taskName(row).ref ?? taskName(row).title,
            detail: taskName(row).ref ? taskName(row).title : null,
            narrow: { task: { id: row.task_id, label: taskName(row).ref ?? taskName(row).title } },
          }
        : { key: '', label: 'No task', detail: 'Runs from a conversation, not a task', narrow: null }
    case 'conversation':
      return row.conversation_id
        ? {
            key: row.conversation_id,
            label: row.conversation_title ?? 'Untitled conversation',
            detail: row.agent,
            narrow: { conversation: { id: row.conversation_id, label: row.conversation_title ?? 'conversation' } },
          }
        : { key: '', label: 'No conversation', detail: null, narrow: null }
    case 'kind':
      return { key: row.kind, label: KIND_LABELS[row.kind], detail: null, narrow: null }
    case 'day': {
      const d = hubDate(row.start_time)
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      return { key, label: formatDay(key), detail: null, narrow: null }
    }
    case 'none':
      return { key: '', label: '', detail: null, narrow: null }
  }
}

/** Groups in the order the operator reads them: days newest first, everything else by cost and
 *  then by count, so the expensive and the busy come first. */
export function groupRows(rows: readonly TraceRow[], grouping: TraceGrouping): TraceGroup[] {
  const byKey = new Map<string, Omit<TraceGroup, 'totals'>>()
  for (const row of rows) {
    const g = groupKey(row, grouping)
    const existing = byKey.get(g.key)
    if (existing) existing.rows.push(row)
    else byKey.set(g.key, { ...g, rows: [row] })
  }
  const groups = [...byKey.values()].map((g) => ({ ...g, totals: totals(g.rows) }))
  if (grouping === 'day') return groups.sort((a, b) => b.key.localeCompare(a.key))
  return groups.sort((a, b) => (b.totals.cost_micros ?? -1) - (a.totals.cost_micros ?? -1) || b.totals.count - a.totals.count)
}
