import { useState, useMemo } from 'react'
import { useTasks } from '@/api/tasks'
import { TaskCard } from './TaskCard'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'

const COLUMNS = [
  { key: 'pending',         label: 'Pending',        accentColor: null as string | null },
  { key: 'assigned',        label: 'Assigned',       accentColor: null as string | null },
  { key: 'in_progress',     label: 'In Progress',    accentColor: 'var(--blue)' },
  { key: 'under_review',    label: 'Under Review',   accentColor: 'var(--amber)' },
  { key: 'completed',       label: 'Completed',      accentColor: null as string | null },
  { key: 'approved',        label: 'Approved',       accentColor: 'var(--green)' },
  { key: 'revision_needed', label: 'Needs Revision', accentColor: 'var(--red)' },
]

export function TasksBoard() {
  const { data: tasks, isLoading } = useTasks()
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [rejectedExpanded, setRejectedExpanded] = useState(false)

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

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Filter chips */}
      {assignees.length > 0 && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 flex-wrap" style={{ borderBottom: '1px solid var(--border)' }}>
          <button
            onClick={() => setActiveFilter(null)}
            style={{
              background: activeFilter === null ? 'var(--surface-3)' : 'var(--surface-2)',
              border: `1px solid ${activeFilter === null ? 'var(--border-hi)' : 'var(--border)'}`,
              borderRadius: 9999,
              fontSize: 11,
              padding: '3px 10px',
              color: activeFilter === null ? 'var(--text)' : 'var(--text-2)',
              cursor: 'pointer',
            }}
          >
            All
          </button>
          {assignees.map((name) => (
            <button
              key={name}
              onClick={() => setActiveFilter(name)}
              style={{
                background: activeFilter === name ? 'var(--surface-3)' : 'var(--surface-2)',
                border: `1px solid ${activeFilter === name ? 'var(--border-hi)' : 'var(--border)'}`,
                borderRadius: 9999,
                fontSize: 11,
                padding: '3px 10px',
                color: activeFilter === name ? 'var(--text)' : 'var(--text-2)',
                cursor: 'pointer',
              }}
            >
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
          {COLUMNS.map(({ key, label, accentColor }) => {
            let col = tasks.filter((t) => t.status === key)
            if (activeFilter !== null) {
              col = col.filter((t) => t.assignee === activeFilter)
            }
            return (
              <div key={key} className="flex flex-col gap-2 overflow-hidden">
                {/* Column header */}
                <div className="flex items-center justify-between mb-0.5 px-0.5">
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
                <div className="space-y-2 overflow-y-auto">
                  {col.map((task) => (
                    <TaskCard key={task.id} task={task} />
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
                style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--red)' }}
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
                {(activeFilter !== null
                  ? rejectedTasks.filter((t) => t.assignee === activeFilter)
                  : rejectedTasks
                ).map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
