import { useTasks } from '@/api/tasks'
import { TaskCard } from './TaskCard'
import { EmptyState } from '@/components/common/EmptyState'

const COLUMNS = [
  { key: 'pending',      label: 'Pending',      accent: false },
  { key: 'in_progress',  label: 'In Progress',  accent: true  },
  { key: 'under_review', label: 'Under Review', accent: false },
  { key: 'completed',    label: 'Completed',    accent: false },
]

export function TasksBoard() {
  const { data: tasks, isLoading } = useTasks()

  if (isLoading) {
    return <div className="p-6 m3-body-medium" style={{ color: 'var(--on-sv)' }}>Loading tasks…</div>
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="p-6">
        <EmptyState icon="task_alt" title="No tasks yet" description="Tasks created by agents will appear here." />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-4 h-full p-3 gap-3 overflow-auto">
      {COLUMNS.map(({ key, label, accent }) => {
        const col = tasks.filter((t) => t.status === key)
        return (
          <div
            key={key}
            className="flex flex-col gap-2.5 rounded-2xl p-3 overflow-auto"
            style={{
              background:   accent
                ? 'color-mix(in srgb, var(--p-cont) 25%, var(--surface-low))'
                : 'var(--surface-low)',
              border: `1px solid ${accent ? 'color-mix(in srgb, var(--primary) 20%, transparent)' : 'var(--outline-variant)'}`,
            }}
          >
            {/* Column header */}
            <div className="flex items-center justify-between mb-0.5 px-0.5">
              <span
                className="m3-label-medium uppercase tracking-widest"
                style={{ color: accent ? 'var(--primary)' : 'var(--on-sv)' }}
              >
                {label}
              </span>
              <span
                className="m3-label-small rounded-full px-2 py-0.5"
                style={{
                  background: accent
                    ? 'color-mix(in srgb, var(--primary) 15%, transparent)'
                    : 'var(--surface-highest)',
                  color: accent ? 'var(--primary)' : 'var(--on-sv)',
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
  )
}
