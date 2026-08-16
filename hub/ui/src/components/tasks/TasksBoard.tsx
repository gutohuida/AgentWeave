import { useEffect, useState, useMemo } from 'react'
import { useTasks } from '@/api/tasks'
import { TaskCard } from './TaskCard'
import { TaskDetailDrawer } from './TaskDetailDrawer'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'
import { useAgents } from '@/api/agents'
import { agentColorVars } from '@/lib/agentColors'
import { useTaskFilterStore } from '@/store/taskFilterStore'

// `blocked` has no column of its own, deliberately. It is not a separate stage of work — it is
// in-progress work that stopped — and giving it a ninth column both widens a board the operator has
// already called crowded and makes a card travel out and back as it blocks and unblocks, which
// reads as progress where there is none. It shows as a treatment on the card instead, inside
// In Progress (`2026-08-10-blocked-and-conversation-binding`, R3).
const STATUSES_IN_PROGRESS = ['in_progress', 'blocked']

const COLUMNS = [
  { key: 'pending',         label: 'Pending',        accentColor: null as string | null, statuses: ['pending'] },
  { key: 'assigned',        label: 'Assigned',       accentColor: null as string | null, statuses: ['assigned'] },
  { key: 'in_progress',     label: 'In Progress',    accentColor: 'var(--blue)',         statuses: STATUSES_IN_PROGRESS },
  { key: 'under_review',    label: 'Under Review',   accentColor: 'var(--amber)',        statuses: ['under_review'] },
  { key: 'completed',       label: 'Completed',      accentColor: null as string | null, statuses: ['completed'] },
  { key: 'approved',        label: 'Approved',       accentColor: 'var(--green)',        statuses: ['approved'] },
  { key: 'revision_needed', label: 'Needs Revision', accentColor: 'var(--red)',          statuses: ['revision_needed'] },
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
  const { data: tasks, isLoading } = useTasks({ excludeArchivedCompleted: activeTaskIds === null })
  const { data: agents = [] } = useAgents()
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

  const assignees = useMemo(() => {
    if (!tasks) return []
    const names = new Set<string>()
    tasks.forEach((t) => { if (t.assignee) names.add(t.assignee) })
    return Array.from(names).sort()
  }, [tasks])

  if (isLoading) {
    return <div className="p-6" style={{ color: 'var(--text-3)' }}>Loading tasks…</div>
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
    <div className="flex flex-col h-full overflow-hidden">
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

      {/* Filter chips */}
      {assignees.length > 0 && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border)' }}>
          <button
            onClick={() => setActiveFilter(null)}
            data-active={activeFilter === null ? 'true' : 'false'}
            className="row-item w-auto rounded-full px-2.5 py-0.5 text-[11px]"
            style={{ border: `1px solid ${activeFilter === null ? 'var(--border-hi)' : 'var(--border)'}` }}
          >
            All
          </button>
          {assignees.map((name) => (
            <button
              key={name}
              onClick={() => setActiveFilter(name)}
              data-active={activeFilter === name ? 'true' : 'false'}
              className="row-item w-auto rounded-full px-2.5 py-0.5 text-[11px]"
              style={{ border: `1px solid ${activeFilter === name ? 'var(--border-hi)' : 'var(--border)'}` }}
            >
              <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full" style={{ background: agentColorVars(colorsByAgent.get(name)).accent }} />
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Kanban */}
      <div className="flex-1 overflow-auto p-3">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(160px, 1fr))',
            gap: 8,
            minWidth: 0,
          }}
        >
          {COLUMNS.map(({ key, label, accentColor, statuses }) => {
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
              <div key={key} className="flex flex-col gap-2 min-w-0">
                {/* Column header. Sticky because the whole grid scrolls as one — without this the
                    headers leave with the content and a long column becomes a list of cards whose
                    status you can no longer see. Operator, 2026-08-10: "when I scroll down I lose
                    what each column means." Opaque background so cards pass behind rather than
                    through, and a negative top offset absorbs the grid's own padding. */}
                <div
                  className="sticky z-10 flex items-center justify-between px-0.5"
                  // The grid's own 12px padding scrolls with the content, so the header pins at
                  // -12 to sit flush with the viewport edge and pads that back to cover cards
                  // passing underneath.
                  style={{ top: -12, background: 'var(--bg)', paddingTop: 12, paddingBottom: 6 }}
                >
                  <span
                    className="text-xs font-medium uppercase tracking-wider"
                    style={{ color: accentColor ?? 'var(--text-3)' }}
                  >
                    {label}
                  </span>
                  <span
                    className="text-[10px] font-semibold rounded-full px-2 py-0.5"
                    style={{
                      background: accentColor ? `${accentColor}20` : 'var(--surface-3)',
                      color: accentColor ?? 'var(--text-2)',
                    }}
                  >
                    {col.length}
                  </span>
                </div>
                {/* No scroll of its own: the grid already scrolls, and a nested scrollport both
                    traps the wheel and gives `sticky` above the wrong container to stick to. */}
                <div className="space-y-2">
                  {col.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      assigneeColorIndex={colorsByAgent.get(task.assignee ?? '')}
                      onOpenRequirement={onOpenRequirement}
                      onOpen={() => setOpenTaskId(task.id)}
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
