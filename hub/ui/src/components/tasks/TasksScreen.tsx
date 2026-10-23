import * as React from 'react'
import { useAgents } from '@/api/agents'
import { readableApiError } from '@/api/client'
import { useSpecDocuments } from '@/api/spec'
import {
  useAllowedTransitions,
  useRetryIntegration,
  useStartWorkOnTask,
  useTask,
  useTasks,
  useUpdateTask,
  type Task,
} from '@/api/tasks'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { QueryErrorNotice } from '@/components/common/QueryErrorNotice'
import { Button } from '@/components/ui/button'
import { toast } from '@/lib/toast'
import { useRequirementTallies } from '@/hooks/useRequirementTallies'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { BOARD_COLUMNS, BoardView, type BoardMoves, type TasksView } from './BoardView'
import type { ColumnDropState } from './BoardColumn'
import { DependencyListView } from './DependencyListView'
import { TaskDetailDrawer } from './TaskDetailDrawer'
import { LoadingThread } from '@/components/common/LoadingThread'

const FOLDS_KEY = 'aw.boardFolds'
const MOVE_INSTRUCTIONS_ID = 'task-board-move-instructions'

function loadFolds(projectId: string | null): Record<string, boolean> {
  if (!projectId) return {}
  try {
    return JSON.parse(localStorage.getItem(`${FOLDS_KEY}.${projectId}`) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

/** The Tasks tab: the compact board (`BoardView`) or the dependency chains, fed from the Hub.
 *
 *  Everything the old `TasksBoard` did lives here, on the new components:
 *  - one drawer for the whole board (F5), opened by a card or by the command palette's
 *    `pendingOpenTaskId` (D3), always reading the freshest copy of the task;
 *  - a scope set from outside (`activeTaskIds`, a coverage row's task link) narrows the board and
 *    says so, and turns off the default that retires an archived document's completed work;
 *  - a truncated page says so (F202);
 *  - drag to an allowed column, or Ctrl+Left/Right on a focused card to the nearest allowed one,
 *    with the Hub's refusal in a toast;
 *  - Start work on a card, and Retry on a card whose approval did not merge. */
export function TasksScreen({
  onOpenRequirement,
  onOpenDocument,
}: {
  /** A requirement, chosen in the drawer: its document and fragment. */
  onOpenRequirement?: (documentPath: string, anchor: string) => void
  /** A dependency chain's "Open document". */
  onOpenDocument?: (documentPath: string) => void
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const activeTaskIds = useTaskFilterStore((state) => state.activeTaskIds)
  const clearActiveTaskIds = useTaskFilterStore((state) => state.clearActiveTaskIds)
  const pendingOpenTaskId = useTaskFilterStore((state) => state.pendingOpenTaskId)
  const clearPendingOpenTaskId = useTaskFilterStore((state) => state.clearPendingOpenTaskId)

  const { data: taskPage, isLoading, isError } = useTasks({ excludeArchivedCompleted: activeTaskIds === null })
  const { data: agents = [], error: agentsError } = useAgents()
  const { data: allowed, error: transitionsError } = useAllowedTransitions()
  const { data: specDocuments } = useSpecDocuments()
  const updateTask = useUpdateTask()
  const startWork = useStartWorkOnTask()
  const retry = useRetryIntegration()

  const [view, setView] = React.useState<TasksView>('board')
  const [folds, setFolds] = React.useState<Record<string, boolean>>(() => loadFolds(projectId))
  const [openTaskId, setOpenTaskId] = React.useState<string | null>(null)
  const [draggedTaskId, setDraggedTaskId] = React.useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = React.useState<string | null>(null)
  const [moveMessage, setMoveMessage] = React.useState('')

  React.useEffect(() => setFolds(loadFolds(projectId)), [projectId])
  const changeFolds = (next: Record<string, boolean>) => {
    setFolds(next)
    if (!projectId) return
    try {
      localStorage.setItem(`${FOLDS_KEY}.${projectId}`, JSON.stringify(next))
    } catch {
      // Persistence is optional.
    }
  }

  React.useEffect(() => {
    if (!pendingOpenTaskId) return
    setOpenTaskId(pendingOpenTaskId)
    clearPendingOpenTaskId()
  }, [pendingOpenTaskId, clearPendingOpenTaskId])

  const allTasks = React.useMemo(() => taskPage?.tasks ?? [], [taskPage])
  const tasks = React.useMemo(
    () => (activeTaskIds === null ? allTasks : allTasks.filter((task) => activeTaskIds.includes(task.id))),
    [allTasks, activeTaskIds],
  )
  const tallies = useRequirementTallies(tasks, specDocuments?.documents ?? [])
  const working = React.useMemo(
    () => new Set(tasks.filter((task) => task.assignee_status === 'running').map((task) => task.id)),
    [tasks],
  )

  const transitions = allowed?.transitions ?? {}
  const canMoveTo = (task: Task | null | undefined, column: string) => {
    if (!task) return false
    const statuses = BOARD_COLUMNS.find((c) => c.key === column)?.statuses as readonly string[] | undefined
    return Boolean(statuses && transitions[task.status]?.includes(statuses[0]!))
  }
  const statusOf = (column: string) => (BOARD_COLUMNS.find((c) => c.key === column)?.statuses[0] ?? column) as string

  const moveTask = (task: Task, column: string) => {
    if (!canMoveTo(task, column) || updateTask.isPending) return
    const status = statusOf(column)
    updateTask.mutate(
      { id: task.id, status },
      {
        onSuccess: () => setMoveMessage(`${task.title} moved to ${status.replace(/_/g, ' ')}.`),
        onError: (error: unknown) =>
          toast({
            title: `Could not move ${task.title}`,
            description: readableApiError(error, 'The Hub refused the move.'),
            tone: 'error',
          }),
      },
    )
  }

  const draggedTask = allTasks.find((task) => task.id === draggedTaskId) ?? null
  const finishDragging = () => {
    setDraggedTaskId(null)
    setDragOverColumn(null)
  }

  const moves: BoardMoves = {
    draggedTaskId,
    instructionsId: MOVE_INSTRUCTIONS_ID,
    dropStateFor: (column): ColumnDropState =>
      !draggedTask
        ? 'idle'
        : !canMoveTo(draggedTask, column)
          ? 'unavailable'
          : dragOverColumn === column
            ? 'active'
            : 'available',
    onDragStart: (task, event) => {
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', task.id)
      setDraggedTaskId(task.id)
      setDragOverColumn(null)
    },
    onDragEnd: finishDragging,
    onDragOverColumn: (column, event) => {
      if (!canMoveTo(draggedTask, column)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
      if (dragOverColumn !== column) setDragOverColumn(column)
    },
    onDropColumn: (column, event) => {
      event.preventDefault()
      if (draggedTask && canMoveTo(draggedTask, column)) moveTask(draggedTask, column)
      finishDragging()
    },
    onMoveByKeyboard: (task, direction) => {
      const current = BOARD_COLUMNS.findIndex((c) => (c.statuses as readonly string[]).includes(task.status))
      if (current < 0) return
      const step = direction === 'left' ? -1 : 1
      for (let index = current + step; index >= 0 && index < BOARD_COLUMNS.length; index += step) {
        const column = BOARD_COLUMNS[index]!.key
        if (canMoveTo(task, column)) {
          moveTask(task, column)
          return
        }
      }
      // Unknown is not "none": with the allowed moves unread, say so rather than that none exist.
      setMoveMessage(
        transitionsError
          ? `The allowed moves could not be read from the Hub, so ${task.title} was not moved.`
          : `No allowed status is available to the ${direction} of ${task.title}.`,
      )
    },
  }

  const onStartWork = (taskId: string, agent: string) => {
    const task = allTasks.find((t) => t.id === taskId)
    if (!task) return
    startWork.mutate(
      { taskId, agent, title: task.title },
      {
        onSuccess: () => toast({ title: `${agent} is starting on it`, tone: 'success' }),
        onError: (error: unknown) =>
          toast({
            title: `Could not start ${agent}`,
            description: readableApiError(error, 'The Hub could not start that run.'),
            tone: 'error',
          }),
      },
    )
  }

  const onRetryIntegration = (taskId: string) => {
    retry.mutate(taskId, {
      onSuccess: (result) => {
        const newest = [...(result.integrations ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
        if (newest?.outcome === 'merged') toast({ title: 'Merged', tone: 'success' })
        else
          toast({
            title: 'Still not merged',
            description: newest?.reason || 'The Hub tried again and the merge did not go through.',
            tone: 'error',
          })
      },
      onError: (error: unknown) =>
        toast({
          title: 'Could not merge again',
          description: readableApiError(error, 'The Hub refused the retry.'),
          tone: 'error',
        }),
    })
  }

  const notices = (
    <>
      {/* The agent filter and Start work's agent menu are built from the roster; unread, both would
          offer nobody. */}
      <QueryErrorNotice failures={[['the agents', agentsError]]} className="aw-board-notice" />
      {taskPage?.has_more ? (
        <div className="aw-board-notice" data-testid="tasks-truncated-banner">
          <Icon name="info" size={14} />
          <span>
            Showing the oldest {allTasks.length} of {taskPage.total} tasks. Filter by agent or open a
            specification&apos;s tasks to see the rest.
          </span>
        </div>
      ) : null}
      {activeTaskIds !== null ? (
        <div className="aw-board-notice" data-testid="tasks-requirement-filter-banner">
          <Icon name="filter_alt" size={14} />
          <span>
            Showing {activeTaskIds.length} task{activeTaskIds.length === 1 ? '' : 's'} linked from the specification
          </span>
          <Button
            variant="ghost"
            size="xs"
            className="aw-board-notice-action"
            data-testid="tasks-requirement-filter-clear"
            onClick={clearActiveTaskIds}
          >
            Show every task
          </Button>
        </div>
      ) : null}
    </>
  )

  let body: React.ReactNode
  if (isLoading) {
    body = (
      <LoadingThread label="Loading tasks" minHeight={240} />
    )
  } else if (isError) {
    body = (
      <div className="aw-board-empty" role="alert">
        <EmptyState
          icon="error_outline"
          title="Could not load tasks"
          description="The board could not reach the Hub. Try again once the connection recovers."
        />
      </div>
    )
  } else if (allTasks.length === 0) {
    body = (
      <div className="aw-board-empty">
        <EmptyState icon="task_alt" title="No tasks yet" description="Tasks an approved specification creates, or an agent adds, appear here." />
      </div>
    )
  }

  // A task opened from elsewhere (a Thread knot) may be archived-completed and so absent from the
  // board's page; read it by id rather than landing on the board with nothing open.
  const pageTask = allTasks.find((task) => task.id === openTaskId) ?? null
  const { data: fetchedTask } = useTask(openTaskId && !pageTask && !isLoading ? openTaskId : null)
  const openTask = pageTask ?? (fetchedTask?.id === openTaskId ? fetchedTask : null)

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="tasks-screen">
      <p id={MOVE_INSTRUCTIONS_ID} className="sr-only">
        Drag this task to an allowed status column. With the card focused, press Control and Left
        Arrow or Control and Right Arrow to move it to the nearest allowed status.
      </p>
      <p className="sr-only" aria-live="polite">
        {moveMessage}
      </p>
      {body ?? (
        <BoardView
          tasks={tasks}
          agents={agents}
          tallies={tallies}
          workingTaskIds={working}
          view={view}
          onViewChange={setView}
          folds={folds}
          onFoldsChange={changeFolds}
          selectedTaskId={openTaskId}
          onOpenTask={setOpenTaskId}
          onRetryIntegration={onRetryIntegration}
          notices={notices}
          moves={moves}
          startAgents={agents.map((agent) => agent.name)}
          onStartWork={onStartWork}
        >
          <DependencyListView
            tasks={tasks}
            documents={(specDocuments?.documents ?? []).map((d) => ({ id: d.id, title: d.title, path: d.path }))}
            onOpenTask={setOpenTaskId}
            onOpenDocument={(path) => onOpenDocument?.(path)}
          />
        </BoardView>
      )}
      <TaskDetailDrawer task={openTask} onClose={() => setOpenTaskId(null)} onOpenRequirement={onOpenRequirement} />
    </div>
  )
}
