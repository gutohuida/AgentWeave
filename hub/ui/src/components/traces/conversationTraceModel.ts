import type { Span, TraceDetail } from '@/api/traces'
import { buildWaterfall, type WaterfallRow } from '@/components/traces/traceModel'
import { hubDate } from '@/lib/hubTime'

/**
 * The pure half of a conversation's trace (spec `a-trace-of-a-whole-conversation`): which runs are
 * shown, the time axis they share with long idle gaps folded into marked breaks, and each row's
 * place on it. Kept apart from the component so a test can drive it with the runs in the order
 * the route returns them.
 */

/** One run of the conversation, as the traces list returns a run's row. */
export interface ConversationRun {
  run_id: string
  trace_id: string
  agent: string | null
  model: string | null
  initiator?: string | null
  run_status: string | null
  status: Span['status']
  status_message: string | null
  start_time: string
  end_time: string | null
  ended: boolean
  cost_usd_micros: number | null
  input_tokens: number | null
  output_tokens: number | null
  model_calls: number
  tool_calls: number
  tool_errors: number
  wait_seconds: number
  span_count: number
}

/** Which runs are shown: a range of turns (1-based, inclusive) and an earliest start. */
export interface RunSelection {
  from: number
  to: number
  /** `all`, or a lower bound on when a run started. */
  since: 'all' | '1h' | '6h' | '24h'
}

/** A gap between runs longer than this is folded into a break. */
export const GAP_FOLD_MS = 20 * 60_000
/** The share of the axis a break takes, and the most all breaks may take together. */
const BREAK_SHARE = 0.03
const BREAKS_MAX_SHARE = 0.3

const SINCE_MS: Record<Exclude<RunSelection['since'], 'all'>, number> = { '1h': 3_600_000, '6h': 6 * 3_600_000, '24h': 24 * 3_600_000 }

function ms(value: string): number {
  return hubDate(value).getTime()
}

export function runEndMs(run: ConversationRun, nowMs: number): number {
  return run.end_time ? ms(run.end_time) : nowMs
}

/** The runs in start order, each with its turn number in the whole conversation. */
export function numberRuns(runs: ConversationRun[]): Array<ConversationRun & { turn: number }> {
  return [...runs].sort((a, b) => ms(a.start_time) - ms(b.start_time)).map((run, i) => ({ ...run, turn: i + 1 }))
}

export function selectRuns<T extends ConversationRun & { turn: number }>(runs: T[], selection: RunSelection, nowMs: number): T[] {
  const floor = selection.since === 'all' ? -Infinity : nowMs - SINCE_MS[selection.since]
  return runs.filter((r) => r.turn >= selection.from && r.turn <= selection.to && ms(r.start_time) >= floor)
}

export type AxisSegment =
  | { kind: 'time'; startMs: number; endMs: number; x0: number; x1: number }
  | { kind: 'break'; startMs: number; endMs: number; x0: number; x1: number }

export interface Axis {
  segments: AxisSegment[]
  /** Where an instant falls on the axis, 0 to 1. */
  at: (tMs: number) => number
  startMs: number
  endMs: number
  /** The time the axis draws to scale: everything but the folded gaps. */
  drawnMs: number
}

/**
 * The shared axis. Runs and the short gaps between them are drawn to scale; a gap longer than
 * GAP_FOLD_MS becomes a break of fixed width, so a conversation that spans a night still shows
 * its turns rather than slivers.
 */
export function buildAxis(runs: ConversationRun[], nowMs: number): Axis {
  if (runs.length === 0) return { segments: [], at: () => 0, startMs: 0, endMs: 0, drawnMs: 0 }
  const spans = runs.map((r) => [ms(r.start_time), runEndMs(r, nowMs)] as const).sort((a, b) => a[0] - b[0])
  // Merge overlapping runs, then split the line where a gap is long enough to fold.
  const pieces: Array<{ kind: 'time' | 'break'; startMs: number; endMs: number }> = []
  let [curStart, curEnd] = spans[0]!
  for (const [s, e] of spans.slice(1)) {
    if (s - curEnd > GAP_FOLD_MS) {
      pieces.push({ kind: 'time', startMs: curStart, endMs: curEnd })
      pieces.push({ kind: 'break', startMs: curEnd, endMs: s })
      curStart = s
      curEnd = e
    } else {
      curEnd = Math.max(curEnd, e)
    }
  }
  pieces.push({ kind: 'time', startMs: curStart, endMs: curEnd })

  const breaks = pieces.filter((p) => p.kind === 'break').length
  const breakShare = breaks ? Math.min(BREAK_SHARE, BREAKS_MAX_SHARE / breaks) : 0
  const drawnMs = pieces.filter((p) => p.kind === 'time').reduce((sum, p) => sum + (p.endMs - p.startMs), 0)
  const timeShare = 1 - breakShare * breaks
  let x = 0
  const segments: AxisSegment[] = pieces.map((p) => {
    const width = p.kind === 'break' ? breakShare : drawnMs > 0 ? ((p.endMs - p.startMs) / drawnMs) * timeShare : timeShare / (pieces.length - breaks)
    const seg = { ...p, x0: x, x1: x + width }
    x += width
    return seg
  })
  const at = (tMs: number) => {
    for (const seg of segments) {
      if (tMs <= seg.endMs) {
        if (tMs <= seg.startMs) return seg.x0
        if (seg.kind === 'break') return seg.x0
        return seg.x0 + ((tMs - seg.startMs) / Math.max(1, seg.endMs - seg.startMs)) * (seg.x1 - seg.x0)
      }
    }
    return 1
  }
  return { segments, at, startMs: pieces[0]!.startMs, endMs: pieces[pieces.length - 1]!.endMs, drawnMs }
}

export interface TimelineRow {
  /** `run` is a turn's own row; `span` one of its spans, shown when the turn is unfolded. */
  kind: 'run' | 'span'
  run: ConversationRun & { turn: number }
  row: WaterfallRow
  x0: number
  x1: number
  /** A span row is drawn on its own turn's scale, not the conversation's: on the shared axis a
   *  ten-minute turn of a day-long conversation is a sliver and its spans would be invisible. */
  zoomed: boolean
}

/** A turn's row, then (when unfolded) its spans below it, each placed on the shared axis. */
export function buildTimeline(
  runs: Array<ConversationRun & { turn: number }>,
  details: Record<string, TraceDetail | undefined>,
  unfolded: ReadonlySet<string>,
  axis: Axis,
  nowMs: number,
): TimelineRow[] {
  const rows: TimelineRow[] = []
  for (const run of runs) {
    const detail = details[run.run_id]
    const waterfall = detail ? buildWaterfall(detail.root, detail.spans, nowMs) : []
    const place = (row: WaterfallRow): [number, number] => {
      const start = ms(row.span.start_time)
      return [axis.at(start), axis.at(start + row.durationMs)]
    }
    const rootRow: WaterfallRow =
      waterfall[0] ?? {
        span: { span_id: run.run_id, trace_id: run.trace_id, parent_span_id: null, name: run.agent ?? 'run', operation: 'invoke_agent', status: run.status, status_message: run.status_message, start_time: run.start_time, end_time: run.end_time, ended: run.ended, attributes: {}, events: [] },
        depth: 0,
        offsetMs: 0,
        durationMs: runEndMs(run, nowMs) - ms(run.start_time),
        open: !run.ended,
      }
    const [rx0, rx1] = place(rootRow)
    rows.push({ kind: 'run', run, row: rootRow, x0: rx0, x1: rx1, zoomed: false })
    if (!unfolded.has(run.run_id)) continue
    const turnMs = Math.max(1, rootRow.durationMs)
    for (const row of waterfall.slice(1)) {
      const x0 = Math.min(1, row.offsetMs / turnMs)
      const x1 = Math.min(1, (row.offsetMs + row.durationMs) / turnMs)
      rows.push({ kind: 'span', run, row, x0, x1, zoomed: true })
    }
  }
  return rows
}

/**
 * Which axis labels are drawn: left to right, a label is kept only when it starts at least
 * `minGap` (a share of the axis) after the last kept one. The others stay in the title of their
 * break or tick, so nothing is lost, only not printed on top of its neighbour.
 */
export function keepLabels(positions: number[], minGap: number): boolean[] {
  let last = -Infinity
  return positions.map((x) => {
    if (x - last < minGap) return false
    last = x
    return true
  })
}

export interface ConversationTotals {
  runs: number
  /** Time the shown runs were running, added up. */
  workingMs: number
  /** From the first shown run's start to the last one's end. */
  elapsedMs: number
  costUsdMicros: number
  unpriced: number
  modelCalls: number
  toolCalls: number
  toolErrors: number
  failedRuns: number
  waitSeconds: number
}

export function conversationTotals(runs: ConversationRun[], nowMs: number): ConversationTotals {
  const t: ConversationTotals = { runs: runs.length, workingMs: 0, elapsedMs: 0, costUsdMicros: 0, unpriced: 0, modelCalls: 0, toolCalls: 0, toolErrors: 0, failedRuns: 0, waitSeconds: 0 }
  let first = Infinity
  let last = -Infinity
  for (const r of runs) {
    const s = ms(r.start_time)
    const e = runEndMs(r, nowMs)
    first = Math.min(first, s)
    last = Math.max(last, e)
    t.workingMs += e - s
    if (r.cost_usd_micros == null) t.unpriced += 1
    else t.costUsdMicros += r.cost_usd_micros
    t.modelCalls += r.model_calls
    t.toolCalls += r.tool_calls
    t.toolErrors += r.tool_errors
    t.waitSeconds += r.wait_seconds
    if (r.status === 'error' || r.run_status === 'failed' || r.run_status === 'stopped') t.failedRuns += 1
  }
  t.elapsedMs = runs.length ? last - first : 0
  return t
}
