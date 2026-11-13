import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import type { Task } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { formatDateTime } from '@/lib/format'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/menu'
import { cardStatus } from '@/lib/taskCardStatus'
import { builderAndReviewer, formatStageAge } from '@/lib/taskStage'
import type { CardMoveProps } from './TaskCardCompact'
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
  working,
  onOpen,
  onRetryIntegration,
  startAgents,
  onStartWork,
  move,
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
  /** The assignee has a live run on this task. */
  working?: boolean
  onOpen: (taskId: string) => void
  onRetryIntegration?: (taskId: string) => void
  /** Agents that can be started on this task; the play menu is absent without them. */
  startAgents?: string[]
  onStartWork?: (taskId: string, agent: string) => void
  /** Drag and keyboard moves between columns, supplied by a board that lets cards change status. */
  move?: CardMoveProps
  /** Present while the board is picking tasks to close together. */
  select?: { checked: boolean; onToggle: () => void }
}) {
  const visual = stageVisual(task.stage)
  const clock = now ?? new Date()
  const reviewed = builderAndReviewer(task)
  const builder = reviewed.builder ?? task.builder ?? task.assignee ?? null
  // The reviewer is whoever holds the task during review, else the one its build names to check it,
  // so a card names who will review it before review starts.
  const reviewer = reviewed.reviewer ?? (task.checker && task.checker !== builder ? task.checker : null)
  const retry = cardStatus(task, working)?.retry && onRetryIntegration ? onRetryIntegration : null
  const canStart = Boolean(startAgents && startAgents.length > 0 && onStartWork)
  const age = task.stage_since ? formatStageAge(task.stage_since, clock) : null
  const waitsOn = task.stage_waits_on ?? null
  // A long waits-on takes the stage line: time at stage gives way, the stage word is kept for
  // screen readers, and the line shows the name alone (the glyph and the title say the rest).
  const longWaits = Boolean(waitsOn && waitsOn.length > WAITS_KEEPS_AGE)
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
      className="aw-tcard aw-reveal-host"
      data-task-id={task.id}
      data-stage={task.stage ?? 'not_started'}
      data-tone={visual.tone}
      data-selected={selected ? 'true' : 'false'}
      data-dragging={move?.dragging ? 'true' : 'false'}
      data-actions={retry || canStart ? 'true' : 'false'}
      draggable={move ? true : undefined}
      onDragStart={move?.onDragStart}
      onDragEnd={move?.onDragEnd}
      style={{ '--stage-tone': TONE_COLOR[visual.tone] } as React.CSSProperties}
    >
      {select ? (
        <input
          type="checkbox"
          className="aw-tcard-select"
          data-testid={`task-select-${task.id}`}
          aria-label={`Select ${task.title}`}
          checked={select.checked}
          onChange={select.onToggle}
        />
      ) : null}
      <button
        type="button"
        data-slot="task-card"
        className="aw-tcard-main"
        data-testid={`task-open-${task.id}`}
        onClick={() => onOpen(task.id)}
        aria-label={`Open ${task.title}`}
        aria-describedby={[`task-stage-text-${task.id}`, move?.instructionsId].filter(Boolean).join(' ')}
        onKeyDown={(event) => {
          if (move && event.ctrlKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
            event.preventDefault()
            move.onMoveByKeyboard(event.key === 'ArrowLeft' ? 'left' : 'right')
          }
        }}
      >
        <span className="aw-tcard-title">
          {task.readable_id ? <span className="aw-tcard-id" data-testid={`task-readable-id-${task.id}`}>{task.readable_id}</span> : null}
          {task.title}
        </span>

        <span id={`task-stage-text-${task.id}`} className="aw-tcard-line aw-tcard-stage" title={stageTitle} aria-label={longWaits ? stageTitle : undefined} data-long-waits={longWaits ? 'true' : 'false'} data-testid={`task-stage-${task.id}`}>
          <span key={task.stage ?? 'none'} className="aw-tcard-glyph" data-moving={visual.moving ? 'true' : 'false'}>
            <Icon name={visual.glyph} size={13} />
          </span>
          <span className="aw-tcard-word" data-yields={longWaits ? 'true' : 'false'}>{visual.word}</span>
          {age && !longWaits ? <span className="aw-tcard-age">{age}</span> : null}
          {waitsOn ? (
            <span className="aw-tcard-waits" data-long={longWaits ? 'true' : 'false'} title={waitsWording(task.stage, waitsOn)}>
              {longWaits ? waitsOn : waitsWording(task.stage, waitsOn)}
            </span>
          ) : null}
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
      {retry || canStart ? (
        <span className="aw-tcard-actions">
          {retry ? (
            <button type="button" data-slot="icon-button" className="aw-icon-button" aria-label={`Retry landing ${task.title}`} title="Retry landing" onClick={() => retry(task.id)}>
              <Icon name="restart_alt" size={13} />
            </button>
          ) : null}
          {canStart ? (
            <span className="aw-reveal">
              <Menu>
                <MenuTrigger data-slot="icon-button" className="aw-icon-button" aria-label={`Start work on ${task.title}`} title="Start an agent on this">
                  <Icon name="play_arrow" size={13} />
                </MenuTrigger>
                <MenuContent align="end">
                  <MenuLabel>Start work</MenuLabel>
                  {startAgents!.map((name) => (
                    <MenuItem key={name} icon="play_arrow" onSelect={() => onStartWork!(task.id, name)}>
                      Start {name} on this
                    </MenuItem>
                  ))}
                </MenuContent>
              </Menu>
            </span>
          ) : null}
        </span>
      ) : null}
      <StageThread stage={task.stage} compact />
    </article>
  )
}

// A long waits-on line takes the room time at stage would have used; the age stays in the stage tooltip.
const WAITS_KEEPS_AGE = 16

function Agent({ name, index, title, icon }: { name: string; index: number | null | undefined; title: string; icon?: string }) {
  const color = agentColorVars(index)
  return (
    <span className="aw-tcard-agent" title={title}>
      {icon ? <Icon name={icon} size={10} style={{ color: color.accent }} /> : <span className="aw-tcard-agent-dot" style={{ background: color.accent }} />}
      <span className="aw-tcard-agent-name">{name}</span>
    </span>
  )
}
