import { useSpecDocuments } from '@/api/spec'
import { useDocumentTasks } from '@/api/tasks'
import { Icon } from '@/components/common/Icon'

interface SpecDocumentTasksLinkProps {
  path: string
  /** Switches to the Tasks tab, filtered to the given task ids — the same prop `SpecCoverageBar`
   *  is already threaded, not a second navigation mechanism. */
  onOpenTasks?: (taskIds: string[]) => void
}

/**
 * "N tasks declared by this document," beside `SpecCoverageBar`.
 *
 * A separate component rather than folded into `SpecCoverageBar`: that bar returns `null` when a
 * document has no requirements and no diagnostics, which is unrelated to whether it declared
 * tasks — folding this in would hide it exactly when it is least discoverable any other way.
 */
export function SpecDocumentTasksLink({ path, onOpenTasks }: SpecDocumentTasksLinkProps) {
  const { data } = useSpecDocuments()
  const document = data?.documents.find((entry) => entry.path === path)
  const { data: tasks } = useDocumentTasks(document?.id ?? null)

  if (!document || !tasks || tasks.length === 0) return null

  const label = `${tasks.length} task${tasks.length === 1 ? '' : 's'} declared by this document`

  return (
    <div
      className="flex shrink-0 items-center gap-1.5 px-3 py-1.5 text-xs"
      data-testid="spec-document-tasks-link"
      style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-2)' }}
    >
      <Icon name="task_alt" size={14} />
      {onOpenTasks ? (
        <button
          type="button"
          onClick={() => onOpenTasks(tasks.map((t) => t.id))}
          style={{ background: 'none', border: 'none', color: 'var(--blue)', cursor: 'pointer', padding: 0 }}
        >
          {label}
        </button>
      ) : (
        <span>{label}</span>
      )}
    </div>
  )
}
