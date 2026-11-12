import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import type { Task } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { formatDateTime } from '@/lib/format'
import { builderAndReviewer, formatStageAge } from '@/lib/taskStage'
import { TONE_COLOR, stageVisual, waitsWording } from '@/lib/taskStageVisual'
import { StageThread } from './StageThread'
import '@/styles/task-redesign.css'

/** The board card, redesigned (`task-card-and-story-redesign`).
 *
 *  A title of at most two lines, then exactly two lines (FR-3): the stage, as a glyph and a word,
 *  its time at stage and what it waits on; then whose it is (the spec's tag, the builder and the
 *  reviewer). Two markers sit at the stage line's end when they apply: failing checks with their
 *  count (FR-5) and a critical priority. A hairline thread along the foot shows how far the task has
 *  come. Everything else (description, branch, commits, requirements, criteria) is in the drawer
 *  and never here (FR-4). */
export function TaskCard({
  task,
  colorOf,
  specTag,
  failedChecks,
  now,
  selected,
  onOpen,
  select,
}: {
  task: Task
  /** An agent's palette index (from the roster), for its name's colour. */
  colorOf?: (agent: string) => number | null | undefined
  /** The short tag of the spec this task belongs to. */
  specTag?: string
  /** How many checks failed in the task's latest check run, before review; 0 or absent shows none. */
  failedChecks?: number
  now?: Date
  selected?: boolean
  onOpen: (taskId: string) => void
  /** Present while the board is picking tasks to close together. */
  select?: { checked: boolean; onToggle: () => void }
}) {
  const visual = stageVisual(task.stage)
  const clock = now ?? new Date()
  const reviewed = builderAndReviewer(task)
  const builder = reviewed.builder ?? task.builder ?? task.assignee ?? null
  const reviewer = reviewed.reviewer
  const age = task.stage_since ? formatStageAge(task.stage_since, clock) : null
  const waitsOn = task.stage_waits_on ?? null
  const stageTitle = [
    visual.word,
    task.stage_detail,
    task.stage_since ? `since ${formatDateTime(task.stage_since, clock)}` : null,
    waitsOn ? waitsWording(task.stage, waitsOn) : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <article
      className="aw-tcard"
      data-task-id={task.id}
      data-stage={task.stage ?? 'not_started'}
      data-tone={visual.tone}
      data-selected={selected ? 'true' : 'false'}
      style={{ '--stage-tone': TONE_COLOR[visual.tone] } as React.CSSProperties}
    >
      {select ? (
        <input
          type="checkbox"
          className="aw-tcard-select"
          aria-label={`Select ${task.title}`}
          checked={select.checked}
          onChange={select.onToggle}
        />
      ) : null}
      <button
        type="button"
        className="aw-tcard-main"
        data-testid={`task-open-${task.id}`}
        onClick={() => onOpen(task.id)}
        aria-label={`${task.title}. ${stageTitle}`}
      >
        <span className="aw-tcard-title">
          {task.readable_id ? <span className="aw-tcard-id">{task.readable_id}</span> : null}
          {task.title}
        </span>

        <span className="aw-tcard-line aw-tcard-stage" title={stageTitle} data-testid={`task-stage-${task.id}`}>
          <span key={task.stage ?? 'none'} className="aw-tcard-glyph" data-moving={visual.moving ? 'true' : 'false'}>
            <Icon name={visual.glyph} size={13} />
          </span>
          <span className="aw-tcard-word">{visual.word}</span>
          {age ? <span className="aw-tcard-age">{age}</span> : null}
          {waitsOn ? <span className="aw-tcard-waits">{waitsWording(task.stage, waitsOn)}</span> : null}
          <span className="aw-tcard-markers">
            {failedChecks && failedChecks > 0 ? (
              <span
                className="aw-tcard-marker"
                data-kind="checks"
                data-testid={`task-failed-checks-${task.id}`}
                title={`${failedChecks} ${failedChecks === 1 ? 'check' : 'checks'} failed on the latest run. Open the task to see which.`}
              >
                <Icon name="x" size={11} />
                {failedChecks}
              </span>
            ) : null}
            {task.priority === 'critical' ? (
              <span className="aw-tcard-marker" data-kind="critical" title="Critical priority">
                <Icon name="flag" size={11} />
              </span>
            ) : null}
          </span>
        </span>

        <span className="aw-tcard-line aw-tcard-people">
          {specTag ? (
            <span className="aw-tcard-tag" title={`Spec: ${specTag}`}>
              {specTag}
            </span>
          ) : null}
          {builder ? <Agent name={builder} index={colorOf?.(builder)} title={`Built by ${builder}`} /> : <span className="aw-tcard-nobody">Nobody yet</span>}
          {reviewer ? (
            <>
              <Icon name="arrow_forward" size={10} className="aw-tcard-arrow" />
              <Agent name={reviewer} index={colorOf?.(reviewer)} title={`Reviewed by ${reviewer}`} icon="visibility" />
            </>
          ) : null}
        </span>
      </button>
      <StageThread stage={task.stage} compact />
    </article>
  )
}

function Agent({ name, index, title, icon }: { name: string; index: number | null | undefined; title: string; icon?: string }) {
  const color = agentColorVars(index)
  return (
    <span className="aw-tcard-agent" title={title} style={{ color: color.accent }}>
      {icon ? <Icon name={icon} size={10} /> : <span className="aw-tcard-agent-dot" style={{ background: color.accent }} />}
      {name}
    </span>
  )
}
