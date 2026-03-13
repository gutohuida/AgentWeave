import { CheckSquare } from 'lucide-react'
import { useTasks } from '@/api/tasks'
import { TaskCard } from './TaskCard'
import { EmptyState } from '@/components/common/EmptyState'

const COLUMNS = [
  { key: 'pending', label: 'Pending' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'under_review', label: 'Under Review' },
  { key: 'completed', label: 'Completed' },
]

export function TasksBoard() {
  const { data: tasks, isLoading } = useTasks()

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading tasks…</div>
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="p-6">
        <EmptyState icon={CheckSquare} title="No tasks yet" description="Tasks created by agents will appear here." />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-4 gap-4 p-6 h-full overflow-auto">
      {COLUMNS.map(({ key, label }) => {
        const col = tasks.filter((t) => t.status === key)
        return (
          <div key={key} className="flex flex-col gap-2">
            <div className="flex items-center justify-between pb-2 border-b">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {label}
              </span>
              <span className="text-xs text-muted-foreground">{col.length}</span>
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
