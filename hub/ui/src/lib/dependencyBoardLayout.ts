import type { Task, TaskBoardEdge } from '@/api/tasks'

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
