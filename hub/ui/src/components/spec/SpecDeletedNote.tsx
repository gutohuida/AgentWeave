import { Button } from '@/components/ui/button'
import { keptDetail } from '@/lib/eventSummary'
import { useSpecDeletionStore } from '@/store/specDeletionStore'

/** One sentence naming the document "Delete document" just removed and the tasks that went with
 *  it (F829). Shown by the screen the operator is left on; dismissed by them. */
export function SpecDeletedNote() {
  const notice = useSpecDeletionStore((s) => s.notice)
  const clear = useSpecDeletionStore((s) => s.clear)
  if (!notice) return null
  const said =
    notice.tasks === 0
      ? `Deleted “${notice.title}”. It had no tasks.`
      : `Deleted “${notice.title}” and its ${notice.tasks} ${notice.tasks === 1 ? 'task' : 'tasks'}.`
  return (
    <div
      role="status"
      data-testid="spec-deleted-note"
      className="aw-spec-deleted-note"
    >
      <span>
        {said}
        {/* F838: a task's branch that held work is kept, and the operator has to be told where. */}
        {(notice.kept ?? []).map((kept) => (
          <span key={kept.task_id} className="block" data-testid="spec-deleted-kept">
            {kept.error
              ? `Could not clean up the checkout of ${kept.task_id}: ${kept.error}`
              : `Kept ${kept.branch ?? 'its branch'}${keptDetail(kept)} from a deleted task.`}
          </span>
        ))}
      </span>
      <Button variant="ghost" size="sm" data-testid="spec-deleted-note-dismiss" onClick={clear}>
        Dismiss
      </Button>
    </div>
  )
}
