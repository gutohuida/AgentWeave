import { MenuItem, MenuLabel } from '@/components/ui/menu'
import { useTaskMoves, type Task } from '@/api/tasks'

/** The body of a card's start menu.
 *
 *  Finished work is reviewed, not worked on again (`a-hand-started-task-reaches-review-and-merge`,
 *  FR-1): on a `completed` task the menu lists "Review with <agent>" for each agent the Hub would
 *  staff as its reviewer — read from `/tasks/{id}/moves`, whose `reviewers` is the mover decision's
 *  own answer and never names the author — and choosing one starts a review turn. Mounted only
 *  while the menu is open, so a board of cards does not read every task's moves. */
export function TaskStartMenuItems({
  task,
  startAgents,
  onStartWork,
  onReviewTask,
}: {
  task: Pick<Task, 'id' | 'status'>
  startAgents?: string[]
  onStartWork?: (taskId: string, agent: string) => void
  onReviewTask?: (taskId: string, agent: string) => void
}) {
  if (task.status === 'completed' && onReviewTask) {
    return <ReviewItems taskId={task.id} onReviewTask={onReviewTask} />
  }
  return (
    <>
      <MenuLabel>Start work</MenuLabel>
      {(startAgents ?? []).map((name) => (
        <MenuItem key={name} icon="play_arrow" onSelect={() => onStartWork?.(task.id, name)}>
          Start {name} on this
        </MenuItem>
      ))}
    </>
  )
}

function ReviewItems({ taskId, onReviewTask }: { taskId: string; onReviewTask: (taskId: string, agent: string) => void }) {
  const { data, isLoading, isError } = useTaskMoves(taskId)
  const reviewers = data?.reviewers ?? []
  return (
    <>
      <MenuLabel>Review</MenuLabel>
      {isLoading ? (
        <MenuItem disabled>Reading who can review it…</MenuItem>
      ) : isError ? (
        <MenuItem disabled>Could not read who can review it</MenuItem>
      ) : reviewers.length === 0 ? (
        <MenuItem disabled>No agent other than its author can review it</MenuItem>
      ) : (
        reviewers.map((name) => (
          <MenuItem key={name} icon="fact_check" onSelect={() => onReviewTask(taskId, name)}>
            Review with {name}
          </MenuItem>
        ))
      )}
    </>
  )
}
