import type { Task, TaskBoardEdge, TaskDependencyRef } from '@/api/tasks'

export interface BoardLayer {
  depth: number
  tasks: Task[]
}

/**
 * Longest-path depth (`task-dependencies` task 8.1): a task sits below **everything** it depends
 * on, not just its first-declared prerequisite. Using the shortest or first path instead would let
 * a card with two prerequisites at different depths sit above one of them.
 *
 * A prerequisite outside this board's own task set — an import naming a task in another document
 * (task 8.7's off-board reference) — contributes nothing to depth; it is drawn as a reference, not
 * a layer, so it cannot be measured against.
 */
export function assignDepths(tasks: Task[], edges: TaskBoardEdge[]): Map<string, number> {
  const onBoard = new Set(tasks.map((t) => t.id))
  const prereqsOf = new Map<string, string[]>()
  for (const t of tasks) prereqsOf.set(t.id, [])
  for (const edge of edges) {
    if (!prereqsOf.has(edge.task_id)) prereqsOf.set(edge.task_id, [])
    prereqsOf.get(edge.task_id)!.push(edge.depends_on_task_id)
  }

  const depth = new Map<string, number>()
  const visiting = new Set<string>()

  function depthOf(id: string): number {
    const cached = depth.get(id)
    if (cached !== undefined) return cached
    // A cycle should never reach the board — `spec_completeness` refuses `dependency_cycle` at
    // proposal — but returning 0 here rather than recursing forever is the difference between a
    // rendering quirk and a hung tab if one ever slips through.
    if (visiting.has(id)) return 0
    visiting.add(id)
    let d = 0
    for (const prereqId of prereqsOf.get(id) ?? []) {
      if (!onBoard.has(prereqId)) continue
      d = Math.max(d, depthOf(prereqId) + 1)
    }
    visiting.delete(id)
    depth.set(id, d)
    return d
  }

  for (const t of tasks) depthOf(t.id)
  return depth
}

/**
 * A task's dependency lifecycle is done and will not change further (task 8.6's "terminal"). Mirrors
 * the backend's `run_task_binding.TERMINAL_FOR_BINDING` — restated rather than imported, since the
 * UI has no shared module path into `hub/hub/`. `rejected` counts as terminal here even though it
 * never reached `approved`: it is resolved, not something a layer is still waiting on.
 */
const TERMINAL_TASK_STATUSES = new Set(['approved', 'rejected'])

export function isTerminalTask(task: Task): boolean {
  return TERMINAL_TASK_STATUSES.has(task.status)
}

/**
 * Off-board prerequisites this board's own tasks name (task 8.7) — an imported entry whose
 * resolved task lives in another document. The board's `edges` list only carries ids; the title,
 * status and owning document come from whichever on-board task's own `prerequisites` named it
 * (`_attach_dependencies` on the backend resolves this for every edge touching the page, on-board
 * or not). Deduped by id since more than one on-board task can share the same off-board
 * prerequisite.
 */
export function offBoardPrerequisites(tasks: Task[]): TaskDependencyRef[] {
  const onBoard = new Set(tasks.map((t) => t.id))
  const byId = new Map<string, TaskDependencyRef>()
  for (const task of tasks) {
    for (const ref of task.prerequisites ?? []) {
      if (!onBoard.has(ref.id)) byId.set(ref.id, ref)
    }
  }
  return [...byId.values()]
}

/**
 * The three stalled states design D8 says look identical as "a card that will not start" but have
 * different remedies — `null` for a task that is not gated at all. `running_on_regressed` (task
 * 8.9) is deliberately not one of these: it is a running task, not a stalled one, and is surfaced
 * on its own card rather than folded into a layer's count.
 *
 * `dependency_state === 'gated'` covers two of the three rows in D8's table alike; the split
 * between them reads each unmet prerequisite's own status, which is already on the card via
 * `prerequisites` (no second fetch) — `completed`/`under_review` means the work is done and
 * nothing is reviewing it yet (D8's middle row, the risk this task mitigates), anything earlier
 * means it is still being worked.
 */
export type DependencyStallState = 'gated' | 'waiting_on_review' | 'gated_on_rejected'

const REVIEW_PENDING_STATUSES = new Set(['completed', 'under_review'])

export function dependencyStallState(task: Task): DependencyStallState | null {
  if (task.dependency_state === 'gated_on_rejected') return 'gated_on_rejected'
  if (task.dependency_state !== 'gated') return null
  const unmet = (task.prerequisites ?? []).filter((p) => p.status !== 'approved' && p.status !== 'rejected')
  if (unmet.length > 0 && unmet.every((p) => REVIEW_PENDING_STATUSES.has(p.status))) {
    return 'waiting_on_review'
  }
  return 'gated'
}

/** Groups tasks by depth, shallowest first — top of the board (task 8.2's top-to-bottom layout). */
export function groupByDepth(tasks: Task[], depth: Map<string, number>): BoardLayer[] {
  const groups = new Map<number, Task[]>()
  for (const t of tasks) {
    const d = depth.get(t.id) ?? 0
    if (!groups.has(d)) groups.set(d, [])
    groups.get(d)!.push(t)
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([layerDepth, layerTasks]) => ({ depth: layerDepth, tasks: layerTasks }))
}
