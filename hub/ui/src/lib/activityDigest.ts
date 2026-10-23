/** The Activity tab's digest: raw Hub events turned into one sentence per thing that happened.
 *
 *  The old Activity view listed every event by its wire name (`queue_entry_delivered`,
 *  `run_triggered`…), ten 57px rows per screen with the same icon and an "Info" badge on each,
 *  while Logs showed the same stream better. Here one agent turn is one row ("Architect worked
 *  3m 59s · 831K tokens · $2.40") carrying the events behind it, and the Hub's own bookkeeping
 *  (context readings, titles written) folds into one quiet line per day.
 *
 *  Pure: events in (any order), days out (newest first). Tested against the Terra replica's log. */
import type { EventLogEntry } from '@/api/logs'
import type { TurnUsage } from '@/api/accounting'
import { hubDate } from '@/lib/hubTime'

export type DigestKind = 'turn' | 'task' | 'message' | 'merge' | 'loop' | 'warning' | 'checkout' | 'background'

export interface DigestRow {
  id: string
  kind: DigestKind
  at: string
  agent: string | null
  /** Bold lead (usually the agent), then the rest of the sentence. */
  lead: string | null
  text: string
  /** A second, muted line: what it was about (conversation, task). */
  detail?: string | null
  /** Right-hand facts, already formatted by the caller's formatter. */
  durationSeconds?: number | null
  tokens?: number | null
  usd?: number | null
  severity: 'info' | 'warn' | 'error'
  /** The events this row stands for, oldest first: what "Show events" reveals. */
  events: EventLogEntry[]
  conversationId?: string | null
  taskId?: string | null
}

export interface DigestDay {
  /** YYYY-MM-DD in local time. */
  day: string
  rows: DigestRow[]
  /** Folded bookkeeping for the day, e.g. "97 context readings · 7 titles written". */
  background: { text: string; events: EventLogEntry[] } | null
}

export interface DigestContext {
  turns?: TurnUsage[]
  conversationTitle?: (id: string) => string | null
  taskTitle?: (id: string) => string | null
}

const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null)

function localDay(iso: string): string {
  const d = hubDate(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const STATUS_WORDS: Record<string, string> = {
  pending: 'pending',
  assigned: 'assigned',
  in_progress: 'in progress',
  completed: 'completed',
  under_review: 'under review',
  approved: 'approved',
  revision_needed: 'sent back for revision',
  rejected: 'rejected',
  blocked: 'blocked',
}

export function buildDigest(events: EventLogEntry[], ctx: DigestContext = {}): DigestDay[] {
  const sorted = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  const usageByRun = new Map((ctx.turns ?? []).map((t) => [t.run_id, t]))
  const runs = new Map<string, EventLogEntry[]>()
  const entryToRun = new Map<string, string>()

  // First pass: which queue entries a run consumed, so the entry's "queued" event joins the run.
  for (const e of sorted) {
    const runId = str(e.data?.run_id)
    const entryId = str(e.data?.entry_id)
    if (e.event_type === 'queue_entry_delivered' && runId && entryId) entryToRun.set(entryId, runId)
  }
  const runOf = (e: EventLogEntry): string | null => {
    if (['run_triggered', 'run_started', 'run_completed', 'run_failed', 'run_stopped', 'queue_entry_delivered'].includes(e.event_type)) return str(e.data?.run_id)
    if (e.event_type === 'queue_entry_queued') return entryToRun.get(str(e.data?.entry_id) ?? '') ?? null
    return null
  }

  const rows: DigestRow[] = []
  const background = new Map<string, EventLogEntry[]>()

  for (const e of sorted) {
    const runId = runOf(e)
    if (runId) {
      const list = runs.get(runId) ?? []
      list.push(e)
      runs.set(runId, list)
      continue
    }
    const d = e.data ?? {}
    const agent = e.agent ?? str(d.agent)
    const severity: DigestRow['severity'] = e.severity === 'error' ? 'error' : e.severity === 'warn' ? 'warn' : 'info'
    const taskId = str(d.task_id) ?? (e.event_type === 'task_updated' ? str(d.id) : null)
    const taskTitle = taskId ? ctx.taskTitle?.(taskId) ?? null : null
    const base: Pick<DigestRow, 'id' | 'at' | 'agent' | 'severity' | 'events' | 'taskId'> = { id: e.id, at: e.timestamp, agent, severity, events: [e], taskId }

    switch (e.event_type) {
      case 'context_warning':
      case 'conversation_titled':
      case 'manager_job_fired':
      case 'run_divergence_resolved': {
        const day = localDay(e.timestamp)
        background.set(day, [...(background.get(day) ?? []), e])
        break
      }
      case 'task_updated': {
        const status = str(d.status) ?? ''
        rows.push({ ...base, kind: 'task', lead: null, text: `Task ${STATUS_WORDS[status] ?? status}`, detail: taskTitle })
        break
      }
      case 'message_created':
        rows.push({ ...base, kind: 'message', agent: str(d.from), lead: str(d.from), text: `wrote to ${str(d.to) ?? 'a peer'}`, detail: str(d.subject) })
        break
      case 'run_diverged': {
        const to = str(d.response_agent)
        const status = STATUS_WORDS[str(d.task_status) ?? ''] ?? str(d.task_status)
        rows.push({
          ...base,
          kind: 'warning',
          lead: agent,
          text: `ended its turn with the task still marked ${status}${to ? `, so ${to} takes over` : ''}`,
          detail: taskTitle,
        })
        break
      }
      case 'permission_denied':
        rows.push({ ...base, kind: 'warning', lead: agent, text: `was refused ${str(d.tool_name) ?? 'a tool'}`, detail: str(d.reason) })
        break
      case 'job_fired':
        rows.push({ ...base, kind: 'loop', lead: str(d.job_name), text: 'fired', detail: agent ? `Runs as ${agent}` : null })
        break
      case 'job_run_skipped':
        rows.push({ ...base, kind: 'loop', lead: str(d.job_name), text: 'skipped a firing', detail: str(d.reason) })
        break
      case 'loop_stopped':
      case 'loop_queue_exhausted': {
        // One row for the pair the Hub writes when a loop ends.
        const prev = rows[rows.length - 1]
        if (prev && prev.kind === 'loop' && prev.text === 'finished' && prev.events[0]!.data?.job_id === d.job_id) {
          prev.events.push(e)
          break
        }
        rows.push({ ...base, kind: 'loop', lead: 'Loop', text: 'finished', detail: str(d.reason) ? `Its ${str(d.reason)}` : 'Its queue is empty' })
        break
      }
      case 'task_worktree_released':
        rows.push({
          ...base,
          kind: 'checkout',
          lead: null,
          text: d.had_uncommitted_changes ? 'Task checkout released with uncommitted changes saved' : 'Task checkout released',
          detail: taskTitle,
        })
        break
      default:
        rows.push({ ...base, kind: severity === 'info' ? 'background' : 'warning', lead: agent, text: e.event_type.replace(/_/g, ' '), detail: null })
    }
  }

  for (const [runId, evs] of runs) {
    const started = evs.find((e) => e.event_type === 'run_started')
    // The Hub ends a turn with exactly one of these (`_RUN_LIFECYCLE_EVENTS`, agent_trigger.py).
    const done = evs.find((e) => ['run_completed', 'run_failed', 'run_stopped'].includes(e.event_type))
    const stopped = done?.event_type === 'run_stopped'
    const first = evs[0]!
    const agent = first.agent ?? str(first.data?.agent)
    const conversationId = evs.map((e) => str(e.data?.conversation_id)).find(Boolean) ?? null
    const usage = usageByRun.get(runId)
    const exit = done?.data?.exit_code
    const failed = done?.event_type === 'run_failed' || (!stopped && typeof exit === 'number' && exit !== 0)
    const seconds = started && done ? (Date.parse(done.timestamp) - Date.parse(started.timestamp)) / 1000 : null
    rows.push({
      id: runId,
      kind: 'turn',
      at: (done ?? started ?? first).timestamp,
      agent,
      lead: agent,
      text: done ? (failed ? 'stopped with an error' : stopped ? 'was stopped' : 'worked') : started ? 'is working' : 'was queued',
      detail: conversationId ? ctx.conversationTitle?.(conversationId) ?? null : null,
      durationSeconds: seconds,
      tokens: usage?.total_tokens ?? null,
      usd: usage?.api_equivalent_usd_micros != null ? usage.api_equivalent_usd_micros / 1e6 : null,
      severity: failed ? 'error' : stopped ? 'warn' : 'info',
      events: evs,
      conversationId,
    })
  }

  const days = new Map<string, DigestRow[]>()
  for (const r of rows) {
    const day = localDay(r.at)
    days.set(day, [...(days.get(day) ?? []), r])
  }
  for (const day of background.keys()) if (!days.has(day)) days.set(day, [])

  return [...days.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([day, dayRows]) => {
      const bg = background.get(day) ?? []
      const count = (t: string) => bg.filter((e) => e.event_type === t).length
      const parts = [
        [count('context_warning'), 'context reading'],
        [count('conversation_titled'), 'conversation title'],
        [count('manager_job_fired'), 'manager job'],
        [count('run_divergence_resolved'), 'divergence resolved'],
      ]
        .filter(([n]) => (n as number) > 0)
        .map(([n, w]) => `${n} ${w}${n === 1 ? '' : w === 'divergence resolved' ? '' : 's'}`)
      return {
        day,
        rows: dayRows.sort((a, b) => b.at.localeCompare(a.at)),
        background: bg.length ? { text: parts.join(' · '), events: bg } : null,
      }
    })
}
