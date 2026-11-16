import * as React from 'react'
import { StatusChip } from '../SpecDocumentBody'
import type { SpecTaskView, TaskStatus } from '../model'
import '@/styles/spec-threads.css'

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

export function ThreadLegend({ states }: { states: ThreadState[] }) {
  if (!states.length) return null
  return (
    <ul className="aw-st-legend" aria-label="Thread colours">
      {states.map((s) => (
        <li key={s}>
          <span className="aw-st-swatch" data-state={s} />
          {THREAD_LABEL[s]}
        </li>
      ))}
    </ul>
  )
}

/** One task, as the spec page lists it. `after` replaces the plain "after …" text with chips. */
export function ThreadTaskCard({
  task,
  all,
  afterChips = false,
  compact = false,
}: {
  task: SpecTaskView
  all: SpecTaskView[]
  afterChips?: boolean
  compact?: boolean
}) {
  const prereqs = task.dependsOn.map((d) => all.find((a) => a.key === d)).filter((t): t is SpecTaskView => Boolean(t))
  return (
    <>
      <div className="aw-sp-task-row">
        <span className="aw-sp-task-title">{task.title}</span>
        <StatusChip status={task.status} />
      </div>
      <div className="aw-sp-task-meta">
        {task.agent ? (
          <span className="aw-sp-agent">
            <span className="aw-sp-agent-dot" />
            {task.agent}
          </span>
        ) : (
          <span className="aw-sp-muted">Not handed out</span>
        )}
        {prereqs.length && afterChips ? (
          <span className="aw-st-after">
            after
            {prereqs.map((p) => (
              <span key={p.key} className="aw-st-afterchip" data-state={threadState(p.status)} title={`${p.title}: ${THREAD_LABEL[threadState(p.status)]}`}>
                <span className="aw-st-afterchip-dot" />
                {p.title}
              </span>
            ))}
          </span>
        ) : prereqs.length && !compact ? (
          <span className="aw-sp-muted">after {prereqs.map((p) => p.title).join(', ')}</span>
        ) : null}
        {!compact ? (
          <span className="aw-sp-task-reqs">
            {task.requirementIds.slice(0, 4).map((id) => (
              <span key={id} className="aw-sp-reqchip aw-st-reqchip">
                {id}
              </span>
            ))}
            {task.requirementIds.length > 4 ? <span className="aw-sp-muted">+{task.requirementIds.length - 4}</span> : null}
          </span>
        ) : null}
      </div>
    </>
  )
}
