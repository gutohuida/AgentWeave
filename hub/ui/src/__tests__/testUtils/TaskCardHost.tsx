import { useState } from 'react'
import type { Task } from '@/api/tasks'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'

/**
 * `TasksScreen` owns one drawer for the whole board and threads `onOpen` into every card (F5).
 * This is the minimal host that reproduces that pairing, so a test can render just "a card" and
 * open it without the rest of the board. Liveness is derived as the screen derives it: a run
 * executing right now is `assignee_status === 'running'`.
 */
export function TaskCardHost({
  task,
  assigneeColorIndex,
  onOpenRequirement,
}: {
  task: Task
  assigneeColorIndex?: number | null
  onOpenRequirement?: (documentPath: string, anchor: string) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <TaskCardCompact
        task={task}
        colorIndex={assigneeColorIndex}
        working={task.assignee_status === 'running'}
        onOpen={() => setOpen(true)}
      />
      <TaskDetailDrawer
        task={open ? task : null}
        onClose={() => setOpen(false)}
        onOpenRequirement={onOpenRequirement}
      />
    </>
  )
}
