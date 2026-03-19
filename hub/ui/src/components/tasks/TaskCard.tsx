import { formatDistanceToNow } from 'date-fns'
import { Task } from '@/api/tasks'
import { Badge, statusVariant, priorityVariant } from '@/components/common/Badge'

interface TaskCardProps {
  task: Task
}

export function TaskCard({ task }: TaskCardProps) {
  return (
    <div className="m3-card-elevated p-4 space-y-2.5 cursor-default">
      <p className="m3-title-small" style={{ color: 'var(--foreground)' }}>{task.title}</p>
      {task.description && (
        <p className="m3-body-small line-clamp-2" style={{ color: 'var(--on-sv)' }}>{task.description}</p>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={statusVariant(task.status)}>{task.status}</Badge>
        <Badge variant={priorityVariant(task.priority)}>{task.priority}</Badge>
        {task.assignee && (
          <Badge variant="secondary">{task.assignee}</Badge>
        )}
      </div>
      <p className="m3-label-small" style={{ color: 'var(--on-sv)', opacity: 0.6 }}>
        {formatDistanceToNow(new Date(task.updated), { addSuffix: true })}
      </p>
    </div>
  )
}
