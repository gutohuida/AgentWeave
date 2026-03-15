import { CheckSquare } from 'lucide-react'
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
    return <div className="p-6 text-sm text-white/40">Loading tasks…</div>
  }

  if (!tasks || tasks.length === 0) {
    return (
      <div className="p-6">
        <EmptyState icon={CheckSquare} title="No tasks yet" description="Tasks created by agents will appear here." />
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
            className={`flex flex-col gap-2.5 rounded-xl p-3 overflow-auto ${accent ? 'glass-accent' : 'glass'}`}
          >
            <div className="flex items-center justify-between mb-0.5">
              <span className={`text-xs font-semibold uppercase tracking-widest ${accent ? 'text-primary/80' : 'text-white/40'}`}>
                {label}
              </span>
              <span className={`rounded-full px-1.5 py-0.5 text-xs font-medium ${accent ? 'bg-primary/15 text-primary ring-1 ring-primary/20' : 'bg-white/8 text-white/40 ring-1 ring-white/10'}`}>
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
