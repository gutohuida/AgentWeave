import { useEffect, useState, useMemo } from 'react'
import { useAllowedTransitions, useTasks, useUpdateTask, type Task } from '@/api/tasks'
import { readableApiError } from '@/api/client'
import { TaskCard } from './TaskCard'
import { TaskDetailDrawer } from './TaskDetailDrawer'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { useAgents } from '@/api/agents'
import { agentColorVars } from '@/lib/agentColors'
import { tint } from '@/lib/colorTint'
import { taskStatusTone } from '@/lib/taskStatusColors'
import { useTaskFilterStore } from '@/store/taskFilterStore'

// `blocked` has no column of its own, deliberately. It is not a separate stage of work — it is
// in-progress work that stopped — and giving it a ninth column both widens a board the operator has
// already called crowded and makes a card travel out and back as it blocks and unblocks, which
// reads as progress where there is none. It shows as a treatment on the card instead, inside
// In Progress (`2026-08-10-blocked-and-conversation-binding`, R3).
const STATUSES_IN_PROGRESS = ['in_progress', 'blocked']

// Column accents come from `taskStatusColors`, not a second copy of the mapping — see that module
// for why (the board and the Overview had already drifted apart on `in_progress`).
//
// `empty` is per column and deliberately not one shared sentence. Seven columns means the empty
// treatment is the most-repeated element on this screen, and "No tasks" seven times says nothing
// about *why* a column is empty or what would fill it. Each one names the state and the move that
// ends it; the icon comes from the existing lucide map via `Icon`, sized down from `EmptyState`'s
// own 52px circle so a column reads as a smaller instance of the same pattern, not a new one.
const COLUMNS = [
  { key: 'pending',         label: 'Pending',        accentColor: taskStatusTone('pending'),         statuses: ['pending'],
    empty: { icon: 'list_alt',    title: 'Nothing pending',   description: 'New work lands here before anyone picks it up.' } },
  { key: 'assigned',        label: 'Assigned',       accentColor: taskStatusTone('assigned'),        statuses: ['assigned'],
    empty: { icon: 'person_add',  title: 'Nothing assigned',  description: 'Assign a pending task to move it here.' } },
  { key: 'in_progress',     label: 'In Progress',    accentColor: taskStatusTone('in_progress'),     statuses: STATUSES_IN_PROGRESS,
    empty: { icon: 'play_arrow',  title: 'Nothing running',   description: 'Start work on an assigned task to move it here.' } },
  { key: 'under_review',    label: 'Under Review',   accentColor: taskStatusTone('under_review'),    statuses: ['under_review'],
    empty: { icon: 'fact_check',  title: 'Nothing to review', description: 'Completed work waits here for your verdict.' } },
  { key: 'completed',       label: 'Completed',      accentColor: taskStatusTone('completed'),       statuses: ['completed'],
    empty: { icon: 'task_alt',    title: 'Nothing completed', description: 'An agent moves its own work here when it is done.' } },
  { key: 'approved',        label: 'Approved',       accentColor: taskStatusTone('approved'),        statuses: ['approved'],
    empty: { icon: 'verified',    title: 'Nothing approved',  description: 'Approving reviewed work moves it here, and merges it.' } },
  { key: 'revision_needed', label: 'Needs Revision', accentColor: taskStatusTone('revision_needed'), statuses: ['revision_needed'],
    empty: { icon: 'edit_note',   title: 'Nothing to redo',   description: 'Work sent back from review lands here.' } },
]

interface TasksBoardProps {
  /** A task's requirement chip, clicked. Threaded to `TaskCard` — the other direction of F4's
   *  cross-tab navigation, alongside `SpecCoverageBar`'s task-count link. */
  onOpenRequirement?: (documentPath: string, anchor: string) => void
}

export function TasksBoard({ onOpenRequirement }: TasksBoardProps = {}) {
  const activeTaskIds = useTaskFilterStore((state) => state.activeTaskIds)
  // Only the board's own default (unscoped) view retires an archived document's completed work —
  // an explicit scope (a coverage-bar or document-tasks-link click) must never hide anything it
  // named, so the exclusion switches off the instant a filter is active.
  const { data: tasks, isLoading, isError } = useTasks({ excludeArchivedCompleted: activeTaskIds === null })
  const { data: agents = [] } = useAgents()
  const { data: allowed } = useAllowedTransitions()
  const updateTask = useUpdateTask()
  const colorsByAgent = useMemo(
    () => new Map(agents.map((agent) => [agent.name, agent.color_index])),
    [agents],
  )
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [rejectedExpanded, setRejectedExpanded] = useState(false)
  // One drawer for the whole board, not one per card (F5) — which task it shows is just an id, so
  // it always reads the freshest copy of the task from `useTasks()` rather than a snapshot taken
  // when it was opened.
  const [openTaskId, setOpenTaskId] = useState<string | null>(null)
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)
  const [moveMessage, setMoveMessage] = useState<string>('')
  const [moveRefusal, setMoveRefusal] = useState<string | null>(null)
  const clearActiveTaskIds = useTaskFilterStore((state) => state.clearActiveTaskIds)
  const pendingOpenTaskId = useTaskFilterStore((state) => state.pendingOpenTaskId)
  const clearPendingOpenTaskId = useTaskFilterStore((state) => state.clearPendingOpenTaskId)

  // The command palette's "open task" action (D3): it can only set intent, since the drawer is
  // this board's own state and the board may not be mounted yet when the selection happens.
  useEffect(() => {
    if (!pendingOpenTaskId) return
    setOpenTaskId(pendingOpenTaskId)
    clearPendingOpenTaskId()
  }, [pendingOpenTaskId, clearPendingOpenTaskId])

  // This is a project-agent filter, not a summary of whichever assignees happen to occur in the
  // current result set. Deriving it from tasks made the whole control disappear on exactly the
  // common board state where work has been decomposed but not assigned yet.
  const assignees = useMemo(
    () => agents.map((agent) => agent.name).sort((a, b) => a.localeCompare(b)),
    [agents],
  )

  const draggedTask = tasks?.find((task) => task.id === draggedTaskId) ?? null
  const transitions = allowed?.transitions ?? {}
  const canMoveTo = (task: Task | null, status: string) =>
    Boolean(task && transitions[task.status]?.includes(status))

  const moveTask = (task: Task, status: string) => {
    if (!canMoveTo(task, status) || updateTask.isPending) return
    setMoveRefusal(null)
    updateTask.mutate(
      { id: task.id, status },
      {
        onSuccess: () => setMoveMessage(`${task.title} moved to ${status.replace(/_/g, ' ')}.`),
        onError: (error: unknown) =>
          setMoveRefusal(readableApiError(error, `The Hub could not move ${task.title}.`)),
      },
    )
  }

  const moveByKeyboard = (task: Task, direction: 'left' | 'right') => {
    const currentIndex = COLUMNS.findIndex((column) => column.statuses.includes(task.status))
    if (currentIndex < 0) return
    const step = direction === 'left' ? -1 : 1
    for (let index = currentIndex + step; index >= 0 && index < COLUMNS.length; index += step) {
      const destination = COLUMNS[index].key
      if (canMoveTo(task, destination)) {
        moveTask(task, destination)
        return
      }
    }
    setMoveMessage(`No allowed status is available to the ${direction} of ${task.title}.`)
  }

  const finishDragging = () => {
    setDraggedTaskId(null)
    setDragOverColumn(null)
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2 p-3" aria-label="Loading tasks">
        {COLUMNS.map((column) => (
          <div key={column.key} className="task-board-column p-2 space-y-2">
            <div className="skeleton h-3 w-20" />
            <div className="skeleton h-24 w-full" />
            <div className="skeleton h-16 w-full" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-6" role="alert">
        <EmptyState
          icon="error_outline"
          title="Could not load tasks"
          description="The task board could not reach the Hub. Try again once the connection recovers."
        />
      </div>
    )
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="p-6">
        <EmptyState icon="task_alt" title="No tasks yet" description="Tasks created by agents will appear here." />
      </div>
    )
  }

  const rejectedTasks = tasks.filter((t) => t.status === 'rejected')
  const openTask = tasks.find((t) => t.id === openTaskId) ?? null

  return (
    <div className="task-board-shell flex flex-col h-full overflow-hidden">
      <p id="task-board-move-instructions" className="sr-only">
        Drag this task to an allowed status column. With the card focused, press Control and Left
        Arrow or Control and Right Arrow to move it to the nearest allowed status.
      </p>
      <p className="sr-only" aria-live="polite">{moveMessage}</p>
      {moveRefusal && (
        <div className="task-board-move-refusal shrink-0" role="alert">
          <Icon name="warning" size={14} />
          <span>{moveRefusal}</span>
          <button type="button" aria-label="Dismiss task move error" onClick={() => setMoveRefusal(null)}>
            <Icon name="close" size={14} />
          </button>
        </div>
      )}
      {/* Set from outside the board — a coverage row's task-count link. Shown above the assignee
          filter chips because it is the reason the operator is looking at a narrowed board at
          all, not one more filter among equals. */}
      {activeTaskIds !== null && (
        <div
          data-testid="tasks-requirement-filter-banner"
          className="shrink-0 flex items-center gap-2 px-4 py-2 text-xs"
          style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-2)', background: 'var(--surface-2)' }}
        >
          <Icon name="filter_alt" size={14} />
          <span>
            Showing {activeTaskIds.length} task{activeTaskIds.length === 1 ? '' : 's'} linked from the
            specification
          </span>
          <button
            type="button"
            data-testid="tasks-requirement-filter-clear"
            onClick={clearActiveTaskIds}
            style={{ background: 'none', border: 'none', color: 'var(--blue)', cursor: 'pointer' }}
          >
            Clear
          </button>
        </div>
      )}

      {/* Project-agent filter. Kept visible even when every current task is unassigned: that is
          when the control explains the available ownership vocabulary instead of vanishing. */}
      {assignees.length > 0 && (
        <div className="task-board-filter shrink-0 flex items-center gap-2 flex-wrap" role="group" aria-label="Filter tasks by agent">
          <button
            data-slot="button"
            onClick={() => setActiveFilter(null)}
            data-active={activeFilter === null ? 'true' : 'false'}
            className="task-filter-chip"
          >
            All
          </button>
          {assignees.map((name) => (
            <button
              data-slot="button"
              key={name}
              onClick={() => setActiveFilter(name)}
              data-active={activeFilter === name ? 'true' : 'false'}
              className="task-filter-chip"
            >
              <span className="task-filter-dot" style={{ background: agentColorVars(colorsByAgent.get(name)).accent }} />
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Kanban */}
      <div className="task-board-scroll flex-1 overflow-auto p-3">
        <div
          className="task-board-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(178px, 1fr))',
            gap: 10,
          }}
        >
          {COLUMNS.map(({ key, label, accentColor, statuses, empty }) => {
            let col = tasks.filter((t) => statuses.includes(t.status))
            if (activeFilter !== null) {
              col = col.filter((t) => t.assignee === activeFilter)
            }
            if (activeTaskIds !== null) {
              col = col.filter((t) => activeTaskIds.includes(t.id))
            }
            // Waiting work first. It is the only kind in this column that needs the operator, and
            // burying it under running work is how a card that is asking for something goes unread.
            col = [...col].sort(
              (a, b) => Number(b.status === 'blocked') - Number(a.status === 'blocked'),
            )
            return (
              // No `overflow-hidden` here: it makes this column the scrollport for `sticky`
              // below, so the header would pin to a box that never scrolls and travel away with
              // the cards — which is exactly the reported symptom.
              <div
                key={key}
                className="task-board-column flex flex-col gap-2 min-w-0"
                data-status={key}
                data-drop-state={
                  !draggedTask
                    ? 'idle'
                    : dragOverColumn === key && canMoveTo(draggedTask, key)
                      ? 'active'
                      : canMoveTo(draggedTask, key)
                        ? 'available'
                        : 'unavailable'
                }
                onDragEnter={(event) => {
                  if (!canMoveTo(draggedTask, key)) return
                  event.preventDefault()
                  setDragOverColumn(key)
                }}
                onDragOver={(event) => {
                  if (!canMoveTo(draggedTask, key)) return
                  event.preventDefault()
                  event.dataTransfer.dropEffect = 'move'
                  if (dragOverColumn !== key) setDragOverColumn(key)
                }}
                onDrop={(event) => {
                  event.preventDefault()
                  if (draggedTask && canMoveTo(draggedTask, key)) moveTask(draggedTask, key)
                  finishDragging()
                }}
              >
                {/* Column header. Sticky because the whole grid scrolls as one — without this the
                    headers leave with the content and a long column becomes a list of cards whose
                    status you can no longer see. Operator, 2026-08-10: "when I scroll down I lose
                    what each column means." Opaque background so cards pass behind rather than
                    through, and a negative top offset absorbs the grid's own padding. */}
                <div
                  className="task-column-header sticky z-10 flex items-center justify-between px-0.5"
                  // The grid's own 12px padding scrolls with the content, so the header pins at
                  // -12 to sit flush with the viewport edge and pads that back to cover cards
                  // passing underneath.
                  style={{ top: -12, paddingTop: 12, paddingBottom: 6 }}
                >
                  <span
                    className="task-column-label"
                    style={{ color: accentColor ?? 'var(--text-3)' }}
                  >
                    {label}
                  </span>
                  <span
                    className="task-column-count"
                    style={{
                      // color-mix, not a `${token}20` suffix: a custom property cannot carry a
                      // concatenated alpha channel — `var(--blue)20` is not a colour, so the whole
                      // declaration was being dropped and the four accented columns rendered their
                      // count with no background at all while the two neutral ones kept theirs.
                      background: accentColor ? tint(accentColor, 18) : 'var(--surface-3)',
                      color: accentColor ?? 'var(--text-2)',
                    }}
                  >
                    {col.length}
                  </span>
                </div>
                {/* No scroll of its own: the grid already scrolls, and a nested scrollport both
                    traps the wheel and gives `sticky` above the wrong container to stick to. */}
                <div className="space-y-2">
                  {col.length === 0 && (
                    <div
                      className="task-column-empty"
                      data-testid={`task-column-empty-${key}`}
                      aria-label={`${label} has no tasks`}
                    >
                      <span className="task-column-empty-icon" aria-hidden="true">
                        <Icon name={empty.icon} size={14} />
                      </span>
                      <span className="task-column-empty-title">{empty.title}</span>
                      <span className="task-column-empty-desc">{empty.description}</span>
                    </div>
                  )}
                  {col.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      assigneeColorIndex={colorsByAgent.get(task.assignee ?? '')}
                      onOpenRequirement={onOpenRequirement}
                      onOpen={() => setOpenTaskId(task.id)}
                      draggable
                      isDragging={draggedTaskId === task.id}
                      isSelected={openTaskId === task.id}
                      moveInstructionsId="task-board-move-instructions"
                      onMoveByKeyboard={(direction) => moveByKeyboard(task, direction)}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = 'move'
                        event.dataTransfer.setData('text/plain', task.id)
                        setDraggedTaskId(task.id)
                        setDragOverColumn(null)
                        setMoveRefusal(null)
                      }}
                      onDragEnd={finishDragging}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {/* Rejected section */}
        {rejectedTasks.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setRejectedExpanded(!rejectedExpanded)}
              className="flex items-center gap-2 w-full text-left py-2"
              style={{ borderTop: '1px solid var(--border)' }}
            >
              <Icon name={rejectedExpanded ? 'expand_less' : 'expand_more'} size={16} style={{ color: 'var(--text-3)' }} />
              <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--red)' }}>
                Rejected
              </span>
              <span
                className="text-[10px] font-semibold rounded-full px-2 py-0.5"
                style={{ background: 'color-mix(in srgb, var(--red) 15%, transparent)', color: 'var(--red)' }}
              >
                {rejectedTasks.length}
              </span>
            </button>
            {rejectedExpanded && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, minmax(200px, 1fr))',
                  gap: 8,
                }}
              >
                {rejectedTasks
                  .filter((t) => activeFilter === null || t.assignee === activeFilter)
                  .filter((t) => activeTaskIds === null || activeTaskIds.includes(t.id))
                  .map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      assigneeColorIndex={colorsByAgent.get(task.assignee ?? '')}
                      onOpenRequirement={onOpenRequirement}
                      onOpen={() => setOpenTaskId(task.id)}
                      draggable
                      isDragging={draggedTaskId === task.id}
                      isSelected={openTaskId === task.id}
                      moveInstructionsId="task-board-move-instructions"
                      onMoveByKeyboard={(direction) => moveByKeyboard(task, direction)}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = 'move'
                        event.dataTransfer.setData('text/plain', task.id)
                        setDraggedTaskId(task.id)
                        setDragOverColumn(null)
                        setMoveRefusal(null)
                      }}
                      onDragEnd={finishDragging}
                    />
                  ))}
              </div>
            )}
          </div>
        )}
      </div>

      <TaskDetailDrawer
        task={openTask}
        onClose={() => setOpenTaskId(null)}
        onOpenRequirement={onOpenRequirement}
      />
    </div>
  )
}
