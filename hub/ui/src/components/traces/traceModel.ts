import type { Span } from '@/api/traces'
import { hubDate } from '@/lib/hubTime'

/**
 * The pure half of the trace view: the span tree, each row's position on the timeline, and the
 * words and colours an operation is shown with. Kept apart from the components so a test can
 * drive it with the page the route actually returns.
 */

export interface WaterfallRow {
  span: Span
  depth: number
  /** Milliseconds from the trace's start to this span's start. */
  offsetMs: number
  /** Milliseconds this span lasted, or has lasted so far while it is open. */
  durationMs: number
  open: boolean
}

/** Attributes whose values are prose or payloads, not short scalars: shown folded, in full. */
export const CONTENT_ATTRIBUTES = new Set([
  'gen_ai.input.messages',
  'gen_ai.output.messages',
  'gen_ai.tool.call.arguments',
  'gen_ai.tool.call.result',
  'aw.queue.content',
  'aw.question.text',
  'aw.question.answer',
])

const OPERATION_LABEL: Record<string, string> = {
  invoke_agent: 'run',
  chat: 'model call',
  execute_tool: 'tool',
  'aw.judge': 'permission',
  'aw.permission_wait': 'waiting',
  'aw.ask_user': 'question',
  'aw.deliver': 'delivery',
}

const OPERATION_TOKEN: Record<string, string> = {
  invoke_agent: 'var(--purple)',
  chat: 'var(--blue)',
  execute_tool: 'var(--green)',
  'aw.judge': 'var(--amber)',
  'aw.permission_wait': 'var(--text-3)',
  'aw.ask_user': 'var(--text-3)',
  'aw.deliver': 'var(--text-2)',
}

export function operationLabel(operation: string): string {
  return OPERATION_LABEL[operation] ?? operation
}

/** The bar's colour. An error is red whatever the operation: it is the one thing to find. */
export function spanToken(span: Pick<Span, 'operation' | 'status'>): string {
  if (span.status === 'error') return 'var(--red)'
  return OPERATION_TOKEN[span.operation] ?? 'var(--text-2)'
}

function ms(value: string): number {
  return hubDate(value).getTime()
}

/** Where an open span is drawn to: the root's end when the run is over, otherwise now. */
export function spanEndMs(span: Span, root: Span, nowMs: number): number {
  if (span.end_time) return ms(span.end_time)
  if (root.end_time) return ms(root.end_time)
  return nowMs
}

/** The trace's extent: from its earliest start to its latest end (or now, while it runs). */
export function traceExtent(root: Span, spans: Span[], nowMs: number): { startMs: number; totalMs: number } {
  let start = ms(root.start_time)
  let end = spanEndMs(root, root, nowMs)
  for (const span of spans) {
    start = Math.min(start, ms(span.start_time))
    end = Math.max(end, spanEndMs(span, root, nowMs))
  }
  return { startMs: start, totalMs: Math.max(0, end - start) }
}

/**
 * The rows of the waterfall, depth-first, each node's children by start time. A span whose
 * parent is not on this page — the trace is paged, so a tool call's model call may be on the
 * previous one — hangs off the root rather than vanishing.
 */
export function buildWaterfall(root: Span, spans: Span[], nowMs: number): WaterfallRow[] {
  const { startMs } = traceExtent(root, spans, nowMs)
  const byId = new Map<string, Span>()
  byId.set(root.span_id, root)
  for (const span of spans) byId.set(span.span_id, span)

  const children = new Map<string, Span[]>()
  for (const span of byId.values()) {
    if (span.span_id === root.span_id) continue
    const parent =
      span.parent_span_id && byId.has(span.parent_span_id) && span.parent_span_id !== span.span_id
        ? span.parent_span_id
        : root.span_id
    const list = children.get(parent) ?? []
    list.push(span)
    children.set(parent, list)
  }
  for (const list of children.values()) {
    list.sort((a, b) => ms(a.start_time) - ms(b.start_time))
  }

  const rows: WaterfallRow[] = []
  const seen = new Set<string>()
  const visit = (span: Span, depth: number) => {
    if (seen.has(span.span_id)) return
    seen.add(span.span_id)
    const begin = ms(span.start_time)
    rows.push({
      span,
      depth,
      offsetMs: Math.max(0, begin - startMs),
      durationMs: Math.max(0, spanEndMs(span, root, nowMs) - begin),
      open: !span.ended && !span.end_time,
    })
    for (const child of children.get(span.span_id) ?? []) visit(child, depth + 1)
  }
  visit(root, 0)
  // A parent cycle would leave spans unvisited; they are still shown, under the root.
  for (const span of byId.values()) if (!seen.has(span.span_id)) visit(span, 1)
  return rows
}

export function formatDuration(durationMs: number): string {
  if (durationMs < 1000) return `${Math.round(durationMs)} ms`
  const seconds = durationMs / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function scalar(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number') return String(value)
  return null
}

/** The short fact beside a span's name: which model, which tool, what was decided. */
export function spanHint(span: Span): string | null {
  const attrs = span.attributes ?? {}
  if (span.operation === 'chat') return scalar(attrs['gen_ai.request.model'])
  if (span.operation === 'execute_tool') return scalar(attrs['gen_ai.tool.name'])
  if (span.operation === 'aw.judge') {
    const allowed = attrs['aw.decision.allowed']
    if (allowed === true) return 'allowed'
    if (allowed === false) return 'denied'
    return null
  }
  if (span.operation === 'invoke_agent') return scalar(attrs['gen_ai.agent.name'])
  return null
}

/** Usage on a model call, as one short line, or null. */
export function spanTokens(span: Span): string | null {
  const input = span.attributes?.['gen_ai.usage.input_tokens']
  const output = span.attributes?.['gen_ai.usage.output_tokens']
  if (typeof input !== 'number' && typeof output !== 'number') return null
  const parts = []
  if (typeof input === 'number') parts.push(`${input.toLocaleString()} in`)
  if (typeof output === 'number') parts.push(`${output.toLocaleString()} out`)
  return parts.join(' · ')
}
