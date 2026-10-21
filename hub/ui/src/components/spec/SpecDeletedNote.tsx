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
      className="flex items-center gap-2 px-4 py-2 text-sm"
      style={{ color: 'var(--text-2)', borderBottom: '1px solid var(--border)' }}
    >
      <span className="flex-1">{said}</span>
      <Button variant="ghost" size="sm" data-testid="spec-deleted-note-dismiss" onClick={clear}>
        Dismiss
      </Button>
    </div>
  )
}
