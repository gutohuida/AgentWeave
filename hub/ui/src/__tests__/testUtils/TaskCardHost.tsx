import { useState } from 'react'
import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'

/**
 * `TasksBoard.tsx` owns one drawer for the whole board and threads `onOpen` into every card
 * (F5). Tests that used to drive `TaskCard`'s own inline expansion now need that same pairing —
 * this is the minimal host that reproduces it, so a test can still render just "a card" and open
 * it, without pulling in the rest of the board.
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
      <TaskCard
        task={task}
        assigneeColorIndex={assigneeColorIndex}
        onOpenRequirement={onOpenRequirement}
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
