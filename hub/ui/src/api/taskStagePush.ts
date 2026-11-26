import type { Query, QueryClient } from '@tanstack/react-query'
import type { CheckState } from '@/lib/checkState'

/** One task's stage as a `task_stage` frame carries it (`hub/hub/task_stage_push.py`): derived by
 *  the Hub once, as every task route derives it. */
export interface PushedStage {
  id: string
  stage?: string | null
  stage_since?: string | null
  stage_detail?: string | null
  stage_waits_on?: string | null
  check_state?: CheckState | null
}

const FIELDS = ['stage', 'stage_since', 'stage_detail', 'stage_waits_on', 'check_state'] as const

/** The reads that carry a task's stage: the task lists, the board, one task, and the build reads
 *  (`['project', pid, 'tasks' | 'builds', ...]`). */
function carriesStages(key: readonly unknown[], pid: string): boolean {
  return key[0] === 'project' && key[1] === pid && (key[2] === 'tasks' || key[2] === 'builds')
}

interface Held {
  row: PushedStage
  /** When it arrived, on the same counter as a read's start. */
  at: number
}

let clock = 0
const held = new WeakMap<QueryClient, Map<string, Map<string, Held>>>()
const startedAt = new WeakMap<Query, number>()
const watching = new WeakMap<QueryClient, () => void>()

/** *value* with every task row among *rows* given its pushed stage: any object whose `id` is one of
 *  them and that carries a `stage` or a `check_state` (a list row, a board card, a prerequisite, a
 *  build-view row). Only the fields a row already has are written, besides those two. Unchanged
 *  parts keep their identity, so nothing re-renders for a frame that changes nothing. */
function patched(value: unknown, rows: Map<string, PushedStage>): unknown {
  if (Array.isArray(value)) {
    let changed = false
    const next = value.map((item) => {
      const p = patched(item, rows)
      if (p !== item) changed = true
      return p
    })
    return changed ? next : value
  }
  if (!value || typeof value !== 'object') return value
  const obj = value as Record<string, unknown>
  let out: Record<string, unknown> | null = null
  for (const [k, v] of Object.entries(obj)) {
    const p = patched(v, rows)
    if (p !== v) (out ??= { ...obj })[k] = p
  }
  const row = typeof obj.id === 'string' ? rows.get(obj.id) : undefined
  if (row && ('stage' in obj || 'check_state' in obj)) {
    for (const field of FIELDS) {
      if (!(field in row)) continue
      if (field !== 'stage' && field !== 'check_state' && !(field in obj)) continue
      if (JSON.stringify(obj[field] ?? null) !== JSON.stringify(row[field] ?? null)) (out ??= { ...obj })[field] = row[field]
    }
  }
  return out ?? value
}

function patchQuery(queryClient: QueryClient, query: Query, rows: Map<string, PushedStage>): void {
  const data = query.state.data
  if (data === undefined) return
  const next = patched(data, rows)
  if (next !== data) queryClient.setQueryData(query.queryKey, next)
}

/** Put a `task_stage` frame into every cached read of *pid* that carries one of its tasks, at once:
 *  every open page gets the same frame at the same moment, so the build view, the board and the
 *  map move together rather than each when its own read answers (TSBVD-11, `same-stage-everywhere`).
 *  The frame is also held, so a read sent before it and answered after cannot put the older stage
 *  back (see `watchStageReads`). */
export function applyStageFrame(queryClient: QueryClient, pid: string | undefined, data: unknown): void {
  const tasks = (data as { tasks?: PushedStage[] } | null)?.tasks
  if (!pid || !Array.isArray(tasks) || tasks.length === 0) return
  watchStageReads(queryClient)
  let byProject = held.get(queryClient)
  if (!byProject) held.set(queryClient, (byProject = new Map()))
  let mine = byProject.get(pid)
  if (!mine) byProject.set(pid, (mine = new Map()))
  const at = ++clock
  const rows = new Map<string, PushedStage>()
  for (const row of tasks) {
    if (!row || typeof row.id !== 'string') continue
    rows.set(row.id, row)
    mine.set(row.id, { row, at })
  }
  for (const query of queryClient.getQueryCache().findAll({ predicate: (q) => carriesStages(q.queryKey, pid) })) {
    patchQuery(queryClient, query, rows)
  }
}

/** Note when each stage read starts, and when one answers, re-apply the frames that arrived after
 *  it was sent: its answer is older than they are. A read sent after a frame is the newer word and
 *  is left as it came. Installed once per client. */
export function watchStageReads(queryClient: QueryClient): () => void {
  const existing = watching.get(queryClient)
  if (existing) return existing
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated') return
    const { query, action } = event
    if (action.type === 'fetch') {
      startedAt.set(query, ++clock)
      return
    }
    if (action.type !== 'success' || action.manual) return
    const pid = query.queryKey[1]
    if (typeof pid !== 'string' || !carriesStages(query.queryKey, pid)) return
    const mine = held.get(queryClient)?.get(pid)
    const sent = startedAt.get(query) ?? 0
    if (!mine) return
    const newer = new Map<string, PushedStage>()
    for (const [id, h] of mine) if (h.at > sent) newer.set(id, h.row)
    if (newer.size > 0) patchQuery(queryClient, query, newer)
  })
  const release = () => {
    unsubscribe()
    watching.delete(queryClient)
    held.delete(queryClient)
  }
  watching.set(queryClient, release)
  return release
}
