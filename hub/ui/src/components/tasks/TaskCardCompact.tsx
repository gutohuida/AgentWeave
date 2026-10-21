import type { DragEventHandler } from 'react'
import { Icon } from '@/components/common/Icon'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/menu'
import type { Task } from '@/api/tasks'
import { cardStatus } from '@/lib/taskCardStatus'
import { agentColorVars } from '@/lib/agentColors'
import { formatAgo, formatDateTime } from '@/lib/format'
import '@/styles/board.css'

/** How a task's requirements stand, as the card summarises them. The container derives it from
 *  document coverage (`useRequirementTallies`). */
export interface RequirementTally {
  verified: number
  rejected: number
  total: number
}

/** Drag and keyboard moves, supplied by a board that lets cards change status. Absent elsewhere,
 *  so a card drawn outside the board never becomes draggable by accident. */
export interface CardMoveProps {
  dragging: boolean
  instructionsId: string
  onDragStart: DragEventHandler<HTMLElement>
  onDragEnd: DragEventHandler<HTMLElement>
  onMoveByKeyboard: (direction: 'left' | 'right') => void
}

/** The board card, compact.
 *
 *  Today's card wrapped its title to four lines, gridded every requirement chip (nine on one
 *  card) and put a seven-line merge failure inside itself, so a 175px column held two cards per
 *  screen. This one is three lines at most: a two-line title, one meta line (requirements, the
 *  assignee, age) and, only when something needs saying, one status line. The status line's full
 *  text is in its title, and everything else lives in the task story the card opens.
 *
 *  Start work stays on the card (it is the one action reached for while scanning the board), as
 *  a play button that appears on hover or focus. */
export function TaskCardCompact({
  task,
  colorIndex,
  tally,
  working,
  now,
  selected,
  onOpen,
  onRetryIntegration,
  startAgents,
  onStartWork,
  move,
}: {
  task: Task
  /** The assignee's palette index (from the roster), for the @name colour. */
  colorIndex?: number | null
  tally?: RequirementTally | null
  /** The assignee has a live run on this task. */
  working?: boolean
  now?: Date
  selected?: boolean
  onOpen: (taskId: string) => void
  onRetryIntegration?: (taskId: string) => void
  /** Agents that can be started on this task; the play menu is absent without them. */
  startAgents?: string[]
  onStartWork?: (taskId: string, agent: string) => void
  move?: CardMoveProps
}) {
  const status = cardStatus(task, working)
  const color = agentColorVars(colorIndex)
  return (
    <article
      className="aw-task-card aw-reveal-host"
      data-task-id={task.id}
      data-selected={selected ? 'true' : 'false'}
      data-status-tone={status?.tone ?? 'none'}
      data-dragging={move?.dragging ? 'true' : 'false'}
      draggable={move ? true : undefined}
      onDragStart={move?.onDragStart}
      onDragEnd={move?.onDragEnd}
    >
      <button
        type="button"
        data-slot="task-card"
        data-testid={`task-open-${task.id}`}
        className="aw-task-card-main"
        onClick={() => onOpen(task.id)}
        title={task.title}
        aria-label={`Open ${task.title}`}
        aria-describedby={move?.instructionsId}
        onKeyDown={(event) => {
          if (move && event.ctrlKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
            event.preventDefault()
            move.onMoveByKeyboard(event.key === 'ArrowLeft' ? 'left' : 'right')
          }
        }}
      >
        <span className="aw-task-card-title">{task.title}</span>
        <span className="aw-task-card-meta">
          {tally && tally.total > 0 ? (
            <span
              className="aw-task-card-reqs"
              data-complete={tally.verified === tally.total ? 'true' : 'false'}
              data-rejected={tally.rejected > 0 ? 'true' : 'false'}
              title={`${tally.verified} of ${tally.total} requirements verified${tally.rejected ? `, ${tally.rejected} rejected` : ''}`}
            >
              {tally.verified === tally.total ? <Icon name="check" size={11} /> : null}
              {tally.verified}/{tally.total} FR
            </span>
          ) : null}
          {task.assignee ? (
            <span className="aw-task-card-assignee" data-testid={`task-assignee-${task.id}`} style={{ color: color.accent }}>
              @{task.assignee}
            </span>
          ) : (
            <span className="aw-task-card-unassigned">Unassigned</span>
          )}
          {task.priority === 'high' || task.priority === 'critical' ? (
            <span className="aw-task-card-priority" title={`${task.priority} priority`}>
              <Icon name="flag" size={11} />
            </span>
          ) : null}
          <span className="aw-task-card-age" title={`Updated ${formatDateTime(task.updated, now)}`}>
            {formatAgo(task.updated, now)}
          </span>
        </span>
      </button>
      {startAgents && startAgents.length > 0 && onStartWork ? (
        <span className="aw-reveal aw-task-card-start">
          <Menu>
            <MenuTrigger
              data-slot="icon-button"
              className="aw-icon-button"
              aria-label={`Start work on ${task.title}`}
              title="Start an agent on this"
            >
              <Icon name="play_arrow" size={13} />
            </MenuTrigger>
            <MenuContent align="end">
              <MenuLabel>Start work</MenuLabel>
              {startAgents.map((name) => (
                <MenuItem key={name} icon="play_arrow" onSelect={() => onStartWork(task.id, name)}>
                  Start {name} on this
                </MenuItem>
              ))}
            </MenuContent>
          </Menu>
        </span>
      ) : null}
      {status ? (
        <div
          className="aw-task-card-status"
          data-tone={status.tone}
          data-testid={`task-card-status-${task.id}`}
          data-reason={status.reason}
          title={status.detail ?? status.text}
        >
          {status.tone === 'working' ? <span className="aw-live-dot aw-pulse" /> : <span className="aw-task-card-status-dot" />}
          <span className="min-w-0 flex-1 truncate">{status.text}</span>
          {status.retry && onRetryIntegration ? (
            <button type="button" data-slot="task-card-action" className="aw-task-card-action" onClick={() => onRetryIntegration(task.id)}>
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}
