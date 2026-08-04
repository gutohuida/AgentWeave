import type { TimelineEntry } from '@/api/agentChat'

/** design.md's "typed timeline, not uniform bubbles" principle: every entry
 * belongs to exactly one of three presentation categories. */
export type EntryCategory = 'message' | 'work' | 'result'

const WORK_OUTPUT_KINDS = new Set(['thinking', 'tool_use', 'tool_result'])
const RESULT_OUTPUT_KINDS = new Set(['status', 'diagnostic'])

export function entryCategory(entry: TimelineEntry): EntryCategory {
  if (entry.kind !== 'agent_output') return 'message'
  if (entry.output_kind && WORK_OUTPUT_KINDS.has(entry.output_kind)) return 'work'
  if (entry.output_kind && RESULT_OUTPUT_KINDS.has(entry.output_kind)) return 'result'
  // 'text' | 'error' | unset — conversational.
  return 'message'
}

export interface TimelineTurn {
  /** null for a legacy row with no recorded run (pre-Phase-3 data). */
  runId: string | null
  entries: TimelineEntry[]
}

export interface GroupedTimeline {
  turns: TimelineTurn[]
  /** Still-queued (undelivered) entries — no run yet, so no turn to belong to. */
  pending: TimelineEntry[]
}

/** Groups delivered entries into turns by run_id, preserving arrival order.
 * One run_id is always one contiguous turn: delivered entries within a run
 * are inserted (and thus already ordered) together at delivery time. */
export function groupIntoTurns(entries: TimelineEntry[]): GroupedTimeline {
  const delivered = entries.filter((e) => e.delivery_state === 'delivered')
  const pending = entries.filter((e) => e.delivery_state !== 'delivered')

  const turns: TimelineTurn[] = []
  const indexByKey = new Map<string, number>()
  for (const entry of delivered) {
    const key = entry.run_id ?? `no-run-${entry.id}`
    let index = indexByKey.get(key)
    if (index === undefined) {
      index = turns.length
      indexByKey.set(key, index)
      turns.push({ runId: entry.run_id ?? null, entries: [] })
    }
    turns[index].entries.push(entry)
  }
  return { turns, pending }
}

/** Pairs a tool_use entry with its tool_result (matching call_id within the
 * same turn), mirroring SharedStreamRenderer's pairing so both renderers
 * agree on "completed" vs "failed" vs "awaiting result". */
export function findPairedResult(
  turnEntries: TimelineEntry[],
  useEntry: TimelineEntry,
): TimelineEntry | undefined {
  const callId = (useEntry.payload as Record<string, unknown> | null | undefined)?.call_id
  if (useEntry.output_kind !== 'tool_use' || !callId) return undefined
  return turnEntries.find(
    (e) =>
      e.output_kind === 'tool_result' &&
      (e.payload as Record<string, unknown> | null | undefined)?.call_id === callId,
  )
}

/** A turn's entries, reduced into blocks in execution order — never partitioned into "all
 * work first, then everything else" (2026-08-04-hub-charcoal-visual-refresh). A block is
 * either one non-work entry, or a run of *consecutive* work entries collapsed into a group,
 * so work never moves ahead of the text that preceded it. */
export type TurnBlock =
  | { kind: 'entry'; id: string; entry: TimelineEntry }
  | { kind: 'work'; id: string; entries: TimelineEntry[] }

export function reduceTurnBlocks(entries: TimelineEntry[]): TurnBlock[] {
  const blocks: TurnBlock[] = []
  for (const entry of entries) {
    if (entryCategory(entry) === 'work') {
      const last = blocks[blocks.length - 1]
      if (last && last.kind === 'work') {
        last.entries.push(entry)
        continue
      }
      blocks.push({ kind: 'work', id: `work-${entry.id}`, entries: [entry] })
    } else {
      blocks.push({ kind: 'entry', id: entry.id, entry })
    }
  }
  return blocks
}

export type RunLifecycleStatus =
  | 'started'
  | 'completed'
  | 'failed'
  | 'stopped'
  | 'interrupted'

const LIFECYCLE_EVENT_STATUS: Record<string, RunLifecycleStatus> = {
  run_started: 'started',
  run_completed: 'completed',
  run_failed: 'failed',
  run_stopped: 'stopped',
  run_interrupted: 'interrupted',
}

/** Builds a run_id -> terminal-status map from the existing run-lifecycle
 * EventLog rows (`/agents/{name}/timeline`) — every one of those events
 * carries `data.run_id` (see hub/hub/api/v1/agent_trigger.py's
 * `_broadcast_run_lifecycle` and run_reconciliation.py). Reused rather than
 * duplicated so the timeline and the Activity tab never disagree about a
 * run's outcome. */
export function runStatusByRunId(
  timelineEvents: Array<{ event_type: string; data?: Record<string, unknown> | null }>,
): Record<string, RunLifecycleStatus> {
  const result: Record<string, RunLifecycleStatus> = {}
  for (const event of timelineEvents) {
    const status = LIFECYCLE_EVENT_STATUS[event.event_type]
    const runId = event.data?.run_id
    if (status && typeof runId === 'string') {
      result[runId] = status
    }
  }
  return result
}
