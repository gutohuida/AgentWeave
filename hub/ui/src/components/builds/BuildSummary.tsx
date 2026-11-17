import type * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { BUILD_STATE, leftOut, leftOutShort, taskStateOf, totalCell, type BuildSummaryModel } from './buildViewModel'
import { CostText } from './BuildView'
import '@/styles/builds.css'

export interface BuildSummaryProps {
  summary: BuildSummaryModel
  /** The build view's address, at a task when one is named. Real links, so a new window works. */
  hrefFor: (task?: string) => string
  /** In-app navigation for a plain click; without it the link is followed. */
  onOpen?: (task?: string) => void
  /** `panel`: the side panel's Running tab at 360px: state, tasks approved, cost, send-backs, what
   *  needs you, the tasks. `strip`: one line on the spec page's build card, whose head and meters
   *  already show the state, the tasks approved and the cost: send-backs, what needs you, the tasks. */
  variant: 'panel' | 'strip'
}

/** A build in a few figures, drawn from the same model as the build view so every count agrees
 *  with it (FR-10, FR-11): state, tasks approved, cost with what it leaves out, send-backs, and
 *  what needs the operator. It opens the view; a task opens the view at that task. */
export function BuildSummary({ summary, hrefFor, onOpen, variant }: BuildSummaryProps) {
  const t = summary.totals
  const state = BUILD_STATE[summary.state]
  const cost = totalCell(t.cost)
  const note = leftOut(t.cost)
  const follow = (task?: string) => (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (!onOpen || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return
    event.preventDefault()
    onOpen(task)
  }
  const openLink = (
    <a className="aw-bs-open" href={hrefFor()} onClick={follow()} aria-label="Open build" data-slot="link-button">
      Open build
      <Icon name="arrow_forward" size={12} />
    </a>
  )
  return (
    <div className="aw-bs" data-variant={variant} data-testid="build-summary" data-build-id={summary.id}>
      {variant === 'panel' ? (
        <>
          <div className="aw-bs-line">
            <span className="aw-bs-state" data-state={summary.state}>
              {summary.state === 'running' ? <span className="aw-bv-live" aria-hidden="true" /> : <Icon name={state.icon} size={12} />}
              {state.label}
            </span>
            <span className="aw-bs-progress" title={`${t.approved} of ${t.tasks} tasks approved`}>
              <span className="aw-bv-bar" aria-hidden="true">
                <span style={{ width: `${t.tasks ? (t.approved / t.tasks) * 100 : 0}%` }} />
              </span>
              <span className="tabular" data-testid="summary-approved">
                {t.approved} of {t.tasks} approved
              </span>
            </span>
          </div>
          <div className="aw-bs-line">
            <Figures summary={summary} cost={cost} note={note} withCost />
            {openLink}
          </div>
          <TaskChips summary={summary} hrefFor={hrefFor} follow={follow} />
        </>
      ) : (
        <div className="aw-bs-line">
          <Figures summary={summary} cost={cost} note={note} withCost={false} />
          <TaskChips summary={summary} hrefFor={hrefFor} follow={follow} />
          {openLink}
        </div>
      )}
    </div>
  )
}

function TaskChips({
  summary,
  hrefFor,
  follow,
}: {
  summary: BuildSummaryModel
  hrefFor: (task?: string) => string
  follow: (task?: string) => (event: React.MouseEvent<HTMLAnchorElement>) => void
}) {
  if (!summary.tasks.length) return <p className="aw-bs-empty">No tasks yet.</p>
  return (
    <ul className="aw-bs-tasks" aria-label="Tasks of this build">
      {summary.tasks.map((task) => {
        const s = taskStateOf(task.status)
        const name = task.ref ?? task.title
        return (
          <li key={task.id}>
            <a
              className="aw-bs-task"
              data-status={task.status}
              data-needs={task.needsOperator ? 'true' : undefined}
              href={hrefFor(task.key)}
              onClick={follow(task.key)}
              aria-label={`Open build at ${name}: ${s.label}${task.needsOperator ? ', needs you' : ''}`}
              title={`${task.ref ? `${task.ref}: ` : ''}${task.title}\n${s.label}${task.needsOperator ? ' · needs you' : ''}`}
            >
              <Icon name={task.needsOperator ? 'alert_triangle' : s.icon} size={11} />
              <span>{task.ref ?? '—'}</span>
            </a>
          </li>
        )
      })}
    </ul>
  )
}

function Figures({ summary, cost, note, withCost }: { summary: BuildSummaryModel; cost: ReturnType<typeof totalCell>; note: string | null; withCost: boolean }) {
  const t = summary.totals
  return (
    <span className="aw-bs-figures">
      {withCost ? (
        <span className="aw-bs-figure" title={note ?? undefined} data-testid="summary-cost">
          <CostText cell={cost} />
          {leftOutShort(t.cost) ? <span className="aw-bv-cost-more">{leftOutShort(t.cost)}</span> : null}
        </span>
      ) : null}
      <span className="aw-bs-figure tabular" data-testid="summary-send-backs">
        <Icon name="undo" size={11} />
        {t.sendBacks} {t.sendBacks === 1 ? 'send-back' : 'send-backs'}
      </span>
      <span className="aw-bs-figure tabular" data-testid="summary-needs" data-attention={t.needsOperator ? 'true' : undefined}>
        {t.needsOperator ? <Icon name="alert_triangle" size={11} /> : null}
        {t.needsOperator ? `${t.needsOperator} ${t.needsOperator === 1 ? 'needs' : 'need'} you` : 'nothing needs you'}
      </span>
    </span>
  )
}
