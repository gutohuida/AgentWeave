import { useState, type DragEventHandler } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { readableApiError } from '@/api/client'
import { Task, useStartWorkOnTask } from '@/api/tasks'
import { useAgents } from '@/api/agents'
import { PriorityBadge, StatusBadge } from '@/components/common/Badge'
import { RowMenu } from '@/components/layout/RowMenu'
import { TaskIntegrationNote } from '@/components/tasks/TaskIntegrationNote'
import { agentColorVars } from '@/lib/agentColors'
import { useRequirementChips } from '@/hooks/useRequirementChips'
import { hubDate } from '@/lib/hubTime'
import { prefersReducedMotion } from '@/lib/motion'

interface TaskCardProps {
  task: Task
  assigneeColorIndex?: number | null
  /** A requirement chip, clicked: which document it lives in (resolved from `document_id`) and
   *  which fragment to scroll to. Omitted where there is nowhere to route to. */
  onOpenRequirement?: (documentPath: string, anchor: string) => void
  /** F5: the card itself never shows description/requirements/status controls any more — it opens
   *  `TaskDetailDrawer` for all of that. The board owns which task is open (one drawer, not one
   *  per card), so this only reports the click. */
  onOpen: () => void
  /** The Kanban board opts cards into native drag-and-drop. Other task surfaces reuse this card
   * without accidentally becoming draggable. */
  draggable?: boolean
  isDragging?: boolean
  onDragStart?: DragEventHandler<HTMLDivElement>
  onDragEnd?: DragEventHandler<HTMLDivElement>
  onMoveByKeyboard?: (direction: 'left' | 'right') => void
  moveInstructionsId?: string
}

const AGENT_STATUS_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  running: {
    color: 'var(--green)',
    bg: 'color-mix(in srgb, var(--green) 10%, transparent)',
    border: 'color-mix(in srgb, var(--green) 25%, transparent)',
  },
  active: {
    color: 'var(--blue)',
    bg: 'color-mix(in srgb, var(--blue) 10%, transparent)',
    border: 'color-mix(in srgb, var(--blue) 25%, transparent)',
  },
  waiting: {
    color: 'var(--amber)',
    bg: 'color-mix(in srgb, var(--amber) 10%, transparent)',
    border: 'color-mix(in srgb, var(--amber) 25%, transparent)',
  },
  idle: {
    color: 'var(--text-3)',
    bg: 'var(--surface-3)',
    border: 'var(--border)',
  },
}

function agentStatusTitle(task: Task): string {
  const status = task.assignee_status ?? 'idle'
  const details = [`worker: ${status}`]
  if (task.assignee_status_msg) details.push(task.assignee_status_msg)
  if (task.assignee_last_seen) {
    details.push(
      `last seen ${formatDistanceToNow(hubDate(task.assignee_last_seen), { addSuffix: true })}`,
    )
  }
  return details.join(' · ')
}

export function TaskCard({
  task,
  assigneeColorIndex,
  onOpenRequirement,
  onOpen,
  draggable = false,
  isDragging = false,
  onDragStart,
  onDragEnd,
  onMoveByKeyboard,
  moveInstructionsId,
}: TaskCardProps) {
  const [startWorkRefusal, setStartWorkRefusal] = useState<string | null>(null)
  const startWork = useStartWorkOnTask()
  const { data: agents } = useAgents()
  const agentNames = (agents ?? []).map((a) => a.name)

  // Which requirement this task serves, without opening the drawer (F4). One chip per
  // `requirement_ids` entry — looked up in `requirement_links` for the statement, the rejected
  // tone, and where to navigate; a bare identifier with no matching link still renders, just
  // without a title or a click target, rather than being silently dropped.
  const chips = useRequirementChips(task)

  const assigneeStatus = task.assignee_status ?? (task.assignee ? 'idle' : null)
  const assigneeStatusStyle = assigneeStatus
    ? AGENT_STATUS_STYLES[assigneeStatus] ?? AGENT_STATUS_STYLES.idle
    : null

  // Waiting work sits in the In Progress column rather than a column of its own (R3), so the card
  // itself has to carry the difference. Purple rather than amber: amber already means "stalled",
  // and these are opposites — one is an agent that dropped the work, the other is an agent that
  // correctly refused to guess. Colouring them alike would teach the operator to read the signal
  // that means "someone did the right thing" as a problem.
  const isBlocked = task.status === 'blocked'
  const blockedAccent = 'var(--purple)'

  /* D12: a slow pulsing green hue around a card whose task has a run executing *right now* —
   * a fact the status badge cannot carry, since a task can read `in_progress` with nothing
   * actually running (that disagreement is `has_open_divergence`, above). `assignee_status`
   * is the Hub's own liveness read (`effective_heartbeat_status`): `"running"` only while a
   * fresh, non-stale heartbeat says so, so this is never a second guess about what the badge
   * already means. Never the sole carrier of the fact (D12): the "running" status pill a few
   * lines below already says the same thing in words. */
  const isLive = assigneeStatus === 'running'
  const reduceMotion = prefersReducedMotion()

  return (
    <div
      data-task-id={task.id}
      data-dragging={isDragging ? 'true' : 'false'}
      data-testid={isLive ? `task-live-${task.id}` : undefined}
      className={['task-card-refined', isLive && !reduceMotion ? 'task-live-pulse' : ''].filter(Boolean).join(' ')}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      style={{
        background: 'var(--surface-2)',
        border: `1px solid ${isBlocked ? `color-mix(in srgb, ${blockedAccent} 45%, transparent)` : 'var(--border)'}`,
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        // The static hue itself — present whether or not the animation class above is, so
        // reduced motion loses only the pulsing, never the cue (task 8.16).
        boxShadow: isLive ? '0 0 0 2px color-mix(in srgb, var(--green) 40%, transparent)' : undefined,
      }}
    >
      {/* F5: the card is a summary now, not a second place to work — everything actionable
          (status transitions, description, requirements-as-written, the divergence policy)
          lives in `TaskDetailDrawer`, opened by clicking anywhere on the card. */}
      <div
        data-slot="button"
        className="task-card-body cursor-pointer"
        role="button"
        tabIndex={0}
        aria-label={`Open ${task.title}`}
        aria-describedby={moveInstructionsId}
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return
          if (event.ctrlKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
            event.preventDefault()
            onMoveByKeyboard?.(event.key === 'ArrowLeft' ? 'left' : 'right')
            return
          }
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onOpen()
          }
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="task-card-title" style={{ color: 'var(--text)' }}>
              {task.title}
            </p>

            {/* Compact description. Always clamped — the full text is a drawer click away. */}
            {task.description && (
              <p className="task-card-description mt-1 line-clamp-1" style={{ color: 'var(--text-3)' }}>
                {task.description}
              </p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {/* Start work on this task. The Hub binds the run and moves the task itself, so this
                is the one path where beginning work and the board agreeing about it are the same
                act rather than two things an agent has to remember to do. Kept on the card, not
                the drawer: it is the one action an operator reaches for while still scanning the
                board, not after opening a specific ticket. */}
            {agentNames.length > 0 && (
              <RowMenu
                label={`Start work on ${task.title}`}
                testId={`task-start-work-${task.id}`}
                icon="play_arrow"
                persistent
                items={agentNames.map((name) => ({
                  id: name,
                  label: `Start ${name} on this`,
                  onSelect: () => {
                    setStartWorkRefusal(null)
                    startWork.mutate(
                      { taskId: task.id, agent: name, title: task.title },
                      {
                        onError: (error: unknown) =>
                          setStartWorkRefusal(readableApiError(error, 'The Hub could not start that run.')),
                      },
                    )
                  },
                }))}
              />
            )}

            {/* The explicit "open" affordance F5 asks for, replacing the old expand/collapse
                chevron — there is no inline expansion left to toggle. */}
            <button
              data-testid={`task-open-${task.id}`}
              aria-label={`Open ${task.title}`}
              onClick={(e) => {
                e.stopPropagation()
                onOpen()
              }}
              className="shrink-0 p-1 rounded transition-colors"
              style={{ color: 'var(--text-3)' }}
            >
              <Icon name="chevron_right" size={18} />
            </button>
          </div>
        </div>

        {/* Which requirement(s) this task serves — visible without opening the drawer, which is
            the whole complaint F4 answers: the connection to the specification used to be
            invisible until the card was opened. Empty when `requirement_ids` is empty or absent,
            no placeholder, matching the card's existing pattern for other optional fields. */}
        {chips.length > 0 && (
          <div
            className="flex flex-wrap items-center gap-1 mt-1.5"
            data-testid={`task-requirement-chips-${task.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            {chips.map((chip) => {
              const clickable = Boolean(onOpenRequirement && chip.clickable)
              return (
                <button
                  key={chip.identifier}
                  type="button"
                  data-testid={`task-requirement-chip-${task.id}-${chip.identifier}`}
                  title={chip.statement ?? chip.identifier}
                  disabled={!clickable}
                  onClick={() => {
                    if (clickable) onOpenRequirement!(chip.documentPath!, chip.anchor)
                  }}
                  className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  style={{
                    background: chip.rejected
                      ? 'color-mix(in srgb, var(--red) 12%, transparent)'
                      : 'var(--surface-3)',
                    border: `1px solid ${
                      chip.rejected ? 'color-mix(in srgb, var(--red) 30%, transparent)' : 'var(--border)'
                    }`,
                    color: chip.rejected ? 'var(--red)' : 'var(--text-2)',
                    cursor: clickable ? 'pointer' : 'default',
                  }}
                >
                  {chip.identifier}
                </button>
              )
            })}
          </div>
        )}

        {/* What this task is waiting for, and who it is waiting on. Said in words rather than left
            to a badge: "blocked" alone puts the operator back where they were when the card said in
            progress and nothing was happening. */}
        {isBlocked && (
          <div
            data-testid={`task-blocked-${task.id}`}
            className="mt-2 flex items-start gap-2 rounded px-2 py-1.5"
            style={{
              background: `color-mix(in srgb, ${blockedAccent} 10%, transparent)`,
              border: `1px solid color-mix(in srgb, ${blockedAccent} 25%, transparent)`,
            }}
          >
            <Icon name="help_circle" size={14} style={{ color: blockedAccent, marginTop: 2 }} />
            <div className="min-w-0">
              <p className="text-[11px] font-medium" style={{ color: blockedAccent }}>
                Waiting on you
              </p>
              {task.blocked_reason && (
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-2)' }}>
                  {task.blocked_reason}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Badges row */}
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <StatusBadge status={task.status} />
          {/* A run ended holding this and nothing has moved it since. Amber rather than red: the
              work is not lost and nothing is broken — it is the operator's attention this needs.
              Clears by itself the moment anyone moves the task.

              "Stalled", not "Dropped": the operator was shown the first label on 2026-08-10 and
              asked *"what is a dropped task?"*. A word only its author understands is not a
              signal. The title says the whole thing, because the badge cannot — what the board
              claims, and that nothing is actually running. */}
          {task.has_open_divergence && (
            <span
              data-testid={`task-divergence-${task.id}`}
              title="A run worked on this and ended without changing its status. Nothing is running now."
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'color-mix(in srgb, var(--amber) 12%, transparent)',
                border: '1px solid color-mix(in srgb, var(--amber) 30%, transparent)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--amber)',
              }}
            >
              <Icon name="alert_triangle" size={12} />
              Stalled
            </span>
          )}
          {/* Task 8.9, design D8: "a running task whose dependency regressed is flagged, not
              stopped." `approved -> revision_needed` is operator-only, so this is rare and always
              an explicit act — red rather than the divergence badge's amber, since this one names
              an actual problem (a prerequisite the gate let this task start against no longer
              holds), not a run that merely stopped reporting in. Nothing here moves the task; the
              gate only guards the `-> in_progress` edge (`dependency_gate.py`), so a task already
              running keeps running. */}
          {task.dependency_state === 'running_on_regressed' && (
            <span
              data-testid={`task-dependency-regressed-${task.id}`}
              title="A prerequisite this task started against has since been sent back for revision or rejected."
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'color-mix(in srgb, var(--red) 12%, transparent)',
                border: '1px solid color-mix(in srgb, var(--red) 30%, transparent)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--red)',
              }}
            >
              <Icon name="warning" size={12} />
              Prerequisite regressed
            </span>
          )}
          <PriorityBadge priority={task.priority} />
          {task.assignee && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--text-2)',
              }}
            >
              <span
                data-testid={`task-assignee-color-${task.assignee}`}
                className="mr-1 h-1.5 w-1.5 rounded-full"
                style={{ background: agentColorVars(assigneeColorIndex).accent }}
              />
              @{task.assignee}
            </span>
          )}
          {assigneeStatus && assigneeStatusStyle && (
            <span
              title={agentStatusTitle(task)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: assigneeStatusStyle.bg,
                border: `1px solid ${assigneeStatusStyle.border}`,
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: assigneeStatusStyle.color,
                textTransform: 'capitalize',
              }}
            >
              <span
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 9999,
                  background: assigneeStatusStyle.color,
                }}
              />
              {assigneeStatus.replace(/_/g, ' ')}
            </span>
          )}
          {task.assigner && task.assigner !== task.assignee && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--surface-3)',
                border: '1px solid var(--border)',
                borderRadius: 9999,
                padding: '1px 6px',
                fontSize: 10,
                fontWeight: 500,
                color: 'var(--text-2)',
              }}
            >
              from: {task.assigner}
            </span>
          )}
        </div>

        {/* Timestamp */}
        <p className="text-[11px] mt-2 tabular-nums" style={{ color: 'var(--text-3)' }}>
          {formatDistanceToNow(hubDate(task.updated), { addSuffix: true })}
        </p>

        {/* A refused "start work". The status-transition menu (and its own refusals) moved into
            the drawer with the rest of the transition controls; this one stays because "start
            work" stayed. */}
        {startWorkRefusal && (
          <p
            data-testid={`task-status-refusal-${task.id}`}
            className="text-[11px] mt-2 p-2 rounded"
            style={{
              color: 'var(--amber)',
              background: 'color-mix(in srgb, var(--amber) 10%, transparent)',
              border: '1px solid color-mix(in srgb, var(--amber) 25%, transparent)',
            }}
          >
            {startWorkRefusal}
          </p>
        )}

        {/* Approval merges, so an approved card owes an answer about where the work went. */}
        <TaskIntegrationNote taskId={task.id} status={task.status} />
      </div>
    </div>
  )
}
