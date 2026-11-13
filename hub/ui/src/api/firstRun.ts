import { useSpecDocuments } from '@/api/spec'
import { useTasks } from '@/api/tasks'

/**
 * Whether the project has no work yet: no task and no specification document. `null` while either
 * is unread, or when either read failed, so nothing is offered on a guess. The first-run panel and
 * the new-conversation suggestions both follow it, so they appear and disappear together.
 */
export function useProjectHasNoWork(): boolean | null {
  const { data: taskPage, error: tasksError } = useTasks()
  const { data: documents, error: documentsError } = useSpecDocuments()
  // A read that failed says nothing about whether there is work: offer nothing on it.
  if (tasksError || documentsError || !taskPage || !documents) return null
  return taskPage.total === 0 && documents.documents.length === 0
}
