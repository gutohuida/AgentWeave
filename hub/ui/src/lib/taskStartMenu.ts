import type { Task } from '@/api/tasks'

/** Whether a card's start menu has anything to offer for this task. */
export function canOfferStart(
  task: Pick<Task, 'status'>,
  startAgents: string[] | undefined,
  onStartWork: unknown,
  onReviewTask: unknown,
): boolean {
  if (task.status === 'completed') return Boolean(onReviewTask)
  return Boolean(startAgents && startAgents.length > 0 && onStartWork)
}
