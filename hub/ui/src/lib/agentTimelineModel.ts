import type { RunLifecycleStatus } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import type { TurnUsage } from '@/api/accounting'

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

/** `runner_parsing.py`'s successful-turn sentinel — `status_event("completed", ...)`, kept on the
 * wire because the Handoff flow's separate SSE broadcast depends on the run having *some* typed
 * end marker to key off (see `agent_trigger.py`'s "Kept alongside the typed lifecycle event"
 * comment) — but the operator does not want its rendered text ("Completed") ending every turn.
 * A `status` entry for a still-open phase (e.g. codex's "plan") is unrelated and still renders. */
export function isSuccessCompletionEntry(entry: TimelineEntry): boolean {
  if (entry.kind !== 'agent_output' || entry.output_kind !== 'status') return false
  const payload = entry.payload as Record<string, unknown> | null | undefined
  return payload?.phase === 'completed'
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
/**
 * run_id -> whole-run duration in seconds, from the lifecycle events' own timestamps.
 *
 * Deliberately derived from persisted events rather than from the live `useElapsedSeconds`
 * counter: the counter measures how long *this browser tab* watched a run, so it is null for
 * every turn that finished before the page loaded, and wrong for one that began before it. The
 * "Worked for 12s" line has to read the same after a refresh as it did when the turn landed.
 *
 * A run with no terminal event yet (still going, or the process died without one) is absent
 * rather than zero — the live indicator covers the first case and nothing should be claimed
 * about the second.
 */
export function runDurationsByRunId(
  timelineEvents: Array<{
    event_type: string
    timestamp: string
    data?: Record<string, unknown> | null
  }>,
): Record<string, number> {
  const startedAt: Record<string, number> = {}
  const endedAt: Record<string, number> = {}

  for (const event of timelineEvents) {
    const runId = event.data?.run_id
    if (typeof runId !== 'string') continue
    const at = Date.parse(event.timestamp)
    if (Number.isNaN(at)) continue
    if (event.event_type === 'run_started') {
      startedAt[runId] = at
    } else if (LIFECYCLE_EVENT_STATUS[event.event_type]) {
      endedAt[runId] = at
    }
  }

  const durations: Record<string, number> = {}
  for (const [runId, start] of Object.entries(startedAt)) {
    const end = endedAt[runId]
    // A clock that went backwards between two rows would otherwise produce a negative
    // "Worked for -3s", which reads as a bug in the product rather than in the clock.
    if (end === undefined || end < start) continue
    durations[runId] = Math.round((end - start) / 1000)
  }
  return durations
}

/**
 * run_id -> total token count, from the accounting API's `recent_turns` (see
 * hub/hub/api/v1/accounting.py and Q7 Gap 5's exploration finding — per-turn figures already
 * exist in the right shape, this is a pure display read of them). An 'unavailable' turn or a
 * null total is omitted rather than shown as zero: the runner genuinely reported nothing, which
 * is a different fact than "used no tokens."
 */
export function tokensByRunId(recentTurns: TurnUsage[]): Record<string, number> {
  const tokens: Record<string, number> = {}
  for (const turn of recentTurns) {
    if (turn.status !== 'measured' || turn.total_tokens === null) continue
    tokens[turn.run_id] = turn.total_tokens
  }
  return tokens
}

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
