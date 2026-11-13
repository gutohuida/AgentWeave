import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import type { AgentSummary } from '@/api/agents'
import type { Task } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { groupByStanding, isFinished } from '@/lib/taskStage'
import { taskStatusTone } from '@/lib/taskStatusColors'
import { BoardColumn, type ColumnDropState } from './BoardColumn'
import { TaskCard } from './TaskCard'
import type { RequirementTally } from './TaskCardCompact'
import { CloseForm } from './LooseTaskActions'
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
  workingTaskIds,
  specTags,
  view,
  onViewChange,
  folds,
  onFoldsChange,
  showFinished = false,
  onShowFinishedChange,
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
  /** Requirement tallies per task id. The card no longer shows them (FR-2); the opened task does. */
  tallies?: Record<string, RequirementTally>
  /** Tasks whose assignee has a live run on them. */
  workingTaskIds: ReadonlySet<string>
  /** Each spec's short tag by document id, shown on its tasks' cards. */
  specTags?: ReadonlyMap<string, string>
  view: TasksView
  onViewChange: (view: TasksView) => void
  /** Column key → folded. Absent means "folded when empty". */
  folds: Record<string, boolean>
  onFoldsChange: (folds: Record<string, boolean>) => void
  /** Whether finished tasks (on main, or closed without landing) are shown; the container remembers it. */
  showFinished?: boolean
  onShowFinishedChange?: (show: boolean) => void
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
  // Picking several tasks to close at once (`tasks-outside-a-flow-move-freely`, FR-9).
  const [selecting, setSelecting] = React.useState(false)
  const [picked, setPicked] = React.useState<ReadonlySet<string>>(new Set())
  const togglePicked = (id: string) =>
    setPicked((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })

  const colorOf = React.useMemo(() => new Map(agents.map((a) => [a.name, a.color_index])), [agents])
  const [revealed, setRevealed] = React.useState<'notOnMain' | 'working' | null>(null)
  const standing = React.useMemo(() => groupByStanding(tasks), [tasks])
  const q = query.trim().toLowerCase()
  const matchesQuery = (t: Task) =>
    t.title.toLowerCase().includes(q) || t.id.includes(q) || (t.readable_id ?? '').toLowerCase().includes(q)
  // Finished tasks stay off the board unless the switch is on; a search still reaches them.
  const visible = tasks.filter(
    (t) =>
      (!agentFilter || t.assignee === agentFilter) &&
      (!q || matchesQuery(t)) &&
      (showFinished || !isFinished(t) || Boolean(q)),
  )
  const hiddenFinished = tasks.filter((t) => isFinished(t) && !visible.includes(t)).length

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
        <label className="aw-board-finished-switch">
          <input
            type="checkbox"
            data-testid="board-show-finished"
            checked={showFinished}
            onChange={(e) => onShowFinishedChange?.(e.target.checked)}
          />
          Show finished
        </label>
        <label className="aw-board-search">
          <Icon name="search" size={13} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            type="search"
            placeholder="Search tasks"
            aria-label="Search tasks"
            className="aw-board-search-input"
          />
        </label>
        <button
          type="button"
          data-slot="filter-chip"
          data-testid="board-select-toggle"
          className="aw-filter-chip"
          data-active={selecting ? 'true' : 'false'}
          aria-pressed={selecting}
          onClick={() => {
            setSelecting(!selecting)
            setPicked(new Set())
          }}
        >
          Select
        </button>
      </div>

      {selecting && picked.size > 0 ? (
        <div className="aw-board-notice" data-testid="board-close-bar">
          <strong>{picked.size} selected</strong>
          <CloseForm
            taskIds={[...picked]}
            outcomes={['done_elsewhere', 'cancelled']}
            onDone={() => setPicked(new Set())}
          />
        </div>
      ) : null}

      {notices}

      {view === 'board' ? (
        <div className="aw-board-standing" data-testid="board-standing">
          <div className="aw-board-standing-counts">
            {([
              ['notOnMain', 'not yet on main'],
              ['working', 'being worked on'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className="aw-board-standing-count"
                data-testid={`board-count-${key}`}
                aria-expanded={revealed === key}
                onClick={() => setRevealed(revealed === key ? null : key)}
              >
                <strong>{standing[key].length}</strong>
                {label}
              </button>
            ))}
          </div>
          {revealed ? (
            <ul className="aw-board-standing-list" data-testid={`board-list-${revealed}`}>
              {standing[revealed].map((t) => (
                <li key={t.id}>
                  <button type="button" onClick={() => onOpenTask(t.id)}>
                    {t.readable_id ? `${t.readable_id} ` : ''}
                    {t.title}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {view === 'board' && !showFinished ? (
        <div className="aw-board-hidden-count" data-testid="board-hidden-finished">
          {hiddenFinished} finished {hiddenFinished === 1 ? 'task is' : 'tasks are'} hidden
        </div>
      ) : null}

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
                    <TaskCard
                      key={task.id}
                      task={task}
                      colorOf={(name) => colorOf.get(name)}
                      specTag={task.spec_document_id ? specTags?.get(task.spec_document_id) : undefined}
                      working={workingTaskIds.has(task.id)}
                      selected={task.id === selectedTaskId}
                      select={selecting ? { checked: picked.has(task.id), onToggle: () => togglePicked(task.id) } : undefined}
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
