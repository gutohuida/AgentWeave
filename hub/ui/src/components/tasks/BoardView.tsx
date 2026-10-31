import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import type { AgentSummary } from '@/api/agents'
import type { Task } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { taskStatusTone } from '@/lib/taskStatusColors'
import { BoardColumn, type ColumnDropState } from './BoardColumn'
import { TaskCardCompact, type RequirementTally } from './TaskCardCompact'
import '@/styles/board.css'

export type TasksView = 'board' | 'dependencies'

/** Moving cards between columns, by drag or by Ctrl+Left/Right on a focused card. The container
 *  owns it because only it knows which transitions the Hub allows. */
export interface BoardMoves {
  draggedTaskId: string | null
  dropStateFor: (columnKey: string) => ColumnDropState
  onDragStart: (task: Task, event: React.DragEvent<HTMLElement>) => void
  onDragEnd: () => void
  onDragOverColumn: (columnKey: string, event: React.DragEvent<HTMLElement>) => void
  onDropColumn: (columnKey: string, event: React.DragEvent<HTMLElement>) => void
  onMoveByKeyboard: (task: Task, direction: 'left' | 'right') => void
  /** The id of the visually hidden sentence that tells a keyboard user how to move a card. */
  instructionsId: string
}

/** Lifecycle order, as today's board (TasksBoard.tsx COLUMNS). `blocked` sits in In progress. */
export const BOARD_COLUMNS = [
  { key: 'pending', label: 'Pending', statuses: ['pending'], empty: 'New work lands here before anyone picks it up.' },
  { key: 'assigned', label: 'Assigned', statuses: ['assigned'], empty: 'Assign a pending task to move it here.' },
  { key: 'in_progress', label: 'In progress', statuses: ['in_progress', 'blocked'], empty: 'Nothing running.' },
  { key: 'under_review', label: 'Under review', statuses: ['under_review'], empty: 'Completed work waits here for a verdict.' },
  { key: 'completed', label: 'Completed', statuses: ['completed'], empty: 'An agent moves its own work here when it is done.' },
  { key: 'revision_needed', label: 'Needs revision', statuses: ['revision_needed'], empty: 'Nothing sent back.' },
  { key: 'approved', label: 'Approved', statuses: ['approved'], empty: 'Nothing approved yet.' },
  { key: 'rejected', label: 'Rejected', statuses: ['rejected'], empty: 'Nothing rejected.' },
] as const

/** The tasks board: a slim toolbar, then the lifecycle columns.
 *
 *  Folding: every empty column starts folded; the operator can fold or open any column and the
 *  choice holds while the column's count is unchanged (`folds`, owned by the container so it can
 *  persist it per project). An empty column that gains a card opens by itself. */
export function BoardView({
  tasks,
  agents,
  tallies,
  workingTaskIds,
  view,
  onViewChange,
  folds,
  onFoldsChange,
  selectedTaskId,
  onOpenTask,
  onRetryIntegration,
  notices,
  scopeControl,
  moves,
  startAgents,
  onStartWork,
  now,
  children,
}: {
  tasks: Task[]
  agents: AgentSummary[]
  /** Requirement tallies per task id. */
  tallies: Record<string, RequirementTally>
  /** Tasks whose assignee has a live run on them. */
  workingTaskIds: ReadonlySet<string>
  view: TasksView
  onViewChange: (view: TasksView) => void
  /** Column key → folded. Absent means "folded when empty". */
  folds: Record<string, boolean>
  onFoldsChange: (folds: Record<string, boolean>) => void
  selectedTaskId?: string | null
  onOpenTask: (taskId: string) => void
  onRetryIntegration: (taskId: string) => void
  /** Banners that explain the board's current scope (a filter from the spec, a truncated page),
   *  shown between the toolbar and the columns. */
  notices?: React.ReactNode
  /** The scope picker, shown first in the toolbar; `tasks` is already in that scope. */
  scopeControl?: React.ReactNode
  moves?: BoardMoves
  /** Agents the card's Start work menu offers. */
  startAgents?: string[]
  onStartWork?: (taskId: string, agent: string) => void
  now?: Date
  /** The Dependencies view, rendered in place of the columns when `view` is dependencies. */
  children?: React.ReactNode
}) {
  const [agentFilter, setAgentFilter] = React.useState<string | null>(null)
  const [query, setQuery] = React.useState('')

  const colorOf = React.useMemo(() => new Map(agents.map((a) => [a.name, a.color_index])), [agents])
  const q = query.trim().toLowerCase()
  const visible = tasks.filter(
    (t) => (!agentFilter || t.assignee === agentFilter) && (!q || t.title.toLowerCase().includes(q) || t.id.includes(q)),
  )

  return (
    <div className="aw-board">
      <div className="aw-board-toolbar">
        <Segmented
          label="Tasks view"
          value={view}
          onChange={onViewChange}
          options={[
            { value: 'board', label: 'Board' },
            { value: 'dependencies', label: 'Dependencies' },
          ]}
        />
        {scopeControl}
        <div className="aw-board-filters" role="group" aria-label="Filter by agent">
          <button
            type="button"
            data-slot="filter-chip"
            className="aw-filter-chip"
            data-active={agentFilter === null ? 'true' : 'false'}
            onClick={() => setAgentFilter(null)}
          >
            Everyone
          </button>
          {agents.map((agent) => {
            const color = agentColorVars(agent.color_index)
            const count = tasks.filter((t) => t.assignee === agent.name).length
            return (
              <button
                key={agent.name}
                type="button"
                data-slot="filter-chip"
                className="aw-filter-chip"
                data-active={agentFilter === agent.name ? 'true' : 'false'}
                onClick={() => setAgentFilter(agentFilter === agent.name ? null : agent.name)}
              >
                <span className="aw-agent-dot" style={{ '--agent-accent': color.accent } as React.CSSProperties} />
                {agent.name}
                <span className="aw-filter-chip-count">{count}</span>
              </button>
            )
          })}
        </div>
        <label className="aw-board-search">
          <Icon name="search" size={13} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a task"
            aria-label="Find a task"
            className="aw-board-search-input"
          />
        </label>
      </div>

      {notices}

      {view === 'dependencies' ? (
        <div className="aw-board-scroll">{children}</div>
      ) : (
        <div className="aw-board-scroll">
          <div className="aw-board-columns">
            {BOARD_COLUMNS.map((column) => {
              // Waiting work first: it is the only kind in a column that needs the operator, and
              // burying it under running work is how a card that is asking goes unread.
              const cards = visible
                .filter((t) => (column.statuses as readonly string[]).includes(t.status))
                .sort((a, b) => Number(isWaiting(b)) - Number(isWaiting(a)))
              const folded = folds[column.key] ?? cards.length === 0
              return (
                <BoardColumn
                  key={column.key}
                  id={column.key}
                  label={column.label}
                  tone={taskStatusTone(column.statuses[0])}
                  count={cards.length}
                  folded={folded}
                  emptyHint={column.empty}
                  onToggleFold={() => onFoldsChange({ ...folds, [column.key]: !folded })}
                  drop={
                    moves
                      ? {
                          state: moves.dropStateFor(column.key),
                          onDragEnter: (event) => moves.onDragOverColumn(column.key, event),
                          onDragOver: (event) => moves.onDragOverColumn(column.key, event),
                          onDrop: (event) => moves.onDropColumn(column.key, event),
                        }
                      : undefined
                  }
                >
                  {cards.map((task) => (
                    <TaskCardCompact
                      key={task.id}
                      task={task}
                      colorIndex={task.assignee ? colorOf.get(task.assignee) : null}
                      tally={tallies[task.id]}
                      working={workingTaskIds.has(task.id)}
                      selected={task.id === selectedTaskId}
                      now={now}
                      onOpen={onOpenTask}
                      onRetryIntegration={onRetryIntegration}
                      startAgents={startAgents}
                      onStartWork={onStartWork}
                      move={
                        moves
                          ? {
                              dragging: moves.draggedTaskId === task.id,
                              instructionsId: moves.instructionsId,
                              onDragStart: (event) => moves.onDragStart(task, event),
                              onDragEnd: moves.onDragEnd,
                              onMoveByKeyboard: (direction) => moves.onMoveByKeyboard(task, direction),
                            }
                          : undefined
                      }
                    />
                  ))}
                </BoardColumn>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function isWaiting(task: Task): boolean {
  return task.status === 'blocked' || Boolean(task.blocked_reason ?? task.awaiting_answer_reason)
}
