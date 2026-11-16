import { StatusChip } from '../SpecDocumentBody'
import type { SpecTaskView } from '../model'
import { THREAD_LABEL, threadState, type ThreadState } from './threadModel'
import '@/styles/spec-threads.css'

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
