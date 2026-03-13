import { formatDistanceToNow } from 'date-fns'
import { Task } from '@/api/tasks'
import { Badge, statusVariant, priorityVariant } from '@/components/common/Badge'

interface TaskCardProps {
  task: Task
}

export function TaskCard({ task }: TaskCardProps) {
  return (
    <div className="rounded-lg border bg-card p-3 shadow-sm space-y-2">
      <p className="text-sm font-medium leading-tight">{task.title}</p>
      {task.description && (
        <p className="text-xs text-muted-foreground line-clamp-2">{task.description}</p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={statusVariant(task.status)}>{task.status}</Badge>
        <Badge variant={priorityVariant(task.priority)}>{task.priority}</Badge>
        {task.assignee && (
          <Badge variant="secondary">{task.assignee}</Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {formatDistanceToNow(new Date(task.updated), { addSuffix: true })}
      </p>
    </div>
  )
}
