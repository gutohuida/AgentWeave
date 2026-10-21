import { Button } from '@/components/ui/button'
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
      <span>{said}</span>
      <Button variant="ghost" size="sm" data-testid="spec-deleted-note-dismiss" onClick={clear}>
        Dismiss
      </Button>
    </div>
  )
}
