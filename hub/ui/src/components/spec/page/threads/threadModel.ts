import * as React from 'react'
import type { TaskStatus } from '../model'

/** What a dependency thread says about its prerequisite. Coloured to match that task's own status
 *  chip, so a thread and the knot it leaves read as one thing. */
export type ThreadState = 'done' | 'active' | 'waiting' | 'rejected'
export const THREAD_STATES: ThreadState[] = ['done', 'active', 'waiting', 'rejected']
export const THREAD_LABEL: Record<ThreadState, string> = { done: 'Done', active: 'In progress', waiting: 'Not started', rejected: 'Sent back' }

export function threadState(status: TaskStatus | string | null | undefined): ThreadState {
  if (status === 'approved') return 'done'
  if (status === 'in_progress' || status === 'completed' || status === 'under_review') return 'active'
  if (status === 'rejected' || status === 'revision_needed') return 'rejected'
  return 'waiting'
}

/** The thread colour of the Hub's stage (`task_stage.py`): on main is done, a send-back or a landing
 *  that did not happen is cut, not started is waiting, and everything between is moving. */
export function stageThreadState(stage: string): ThreadState {
  if (stage === 'on_main') return 'done'
  if (stage === 'sent_back' || stage === 'did_not_land' || stage === 'closed') return 'rejected'
  if (stage === 'not_started') return 'waiting'
  return 'active'
}

/** Anything drawn as a node with prerequisites: a spec's planned task, or a task on the board. */
export interface GraphNode {
  key: string
  dependsOn: string[]
}

/** The task itself plus everything upstream and downstream of it. */
export function chainOf(key: string, all: GraphNode[]): Set<string> {
  const seen = new Set<string>([key])
  const walk = (next: (k: string) => string[]) => {
    const stack = [key]
    const visited = new Set([key])
    while (stack.length) {
      for (const n of next(stack.pop()!)) if (!visited.has(n)) { visited.add(n); seen.add(n); stack.push(n) }
    }
  }
  walk((k) => all.find((t) => t.key === k)?.dependsOn ?? [])
  walk((k) => all.filter((t) => t.dependsOn.includes(k)).map((t) => t.key))
  return seen
}

/** Hover or focus on a task lights its chain and dims the rest. */
export function useChain(all: GraphNode[]) {
  const [hot, setHot] = React.useState<string | null>(null)
  const chain = React.useMemo(() => (hot ? chainOf(hot, all) : null), [hot, all])
  const lit = (key: string) => (chain ? (chain.has(key) ? 'on' : 'dim') : undefined)
  const edgeLit = (from: string, to: string) => (chain ? (chain.has(from) && chain.has(to) ? 'on' : 'dim') : undefined)
  const bind = (key: string) => ({
    onMouseEnter: () => setHot(key),
    onMouseLeave: () => setHot(null),
    onFocus: () => setHot(key),
    onBlur: () => setHot(null),
  })
  return { lit, edgeLit, bind }
}
