import { useEffect, useRef, useState } from 'react'
import { readableApiError } from '@/api/client'
import { useDeleteProject, type ProjectSummary } from '@/api/projects'
import { Button } from '@/components/ui/button'
import { useDialogFocus } from '@/hooks/useDialogFocus'

/**
 * Type-to-confirm before an irreversible delete (`design.md` D7) — the operator must reproduce
 * the project's exact current name, case-sensitive, before Delete enables. No other destructive
 * control in this product removes this much at once, so no lighter existing pattern (a single
 * confirm click, as runner-delete uses) is reused here.
 */
export function DeleteProjectDialog({
  project,
  onClose,
  onDeleted,
}: {
  project: ProjectSummary | null
  onClose: () => void
  onDeleted: () => void
}) {
  const [typed, setTyped] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const deleteProject = useDeleteProject(project?.id ?? '')
  const open = !!project

  useEffect(() => {
    if (!open) return
    setTyped('')
    deleteProject.reset()
    // The mutation object changes identity as its state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, project?.id])
  useDialogFocus(open, panelRef, onClose)

  if (!project) return null

  // Trimmed at the edges only — an operator retyping the exact name should not be tripped up by
  // a stray leading/trailing space, but the comparison otherwise stays case-sensitive per D7.
  const canDelete = typed.trim() === project.name && !deleteProject.isPending

  const submit = () => {
    if (!canDelete) return
    deleteProject.mutate(undefined, { onSuccess: onDeleted })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-project-title"
    >
      <div ref={panelRef} className="lifted-surface w-[min(440px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="delete-project-title" className="text-sm font-semibold" style={{ color: 'var(--red)' }}>
          Delete “{project.name}”
        </h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          This removes the project from AgentWeave — its agents, conversations, tasks, and every
          other record — permanently. The folder on disk is never touched.
        </p>

        <label className="mt-4 block text-xs">
          Type <strong>{project.name}</strong> to confirm
          <input
            autoFocus
            aria-label="Project name to confirm"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') submit()
            }}
            className="mt-1 block w-full rounded-md px-3 py-2"
            style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
          />
        </label>

        {deleteProject.error && (
          <div role="alert" className="mt-3 rounded-md px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--red)' }}>
            {readableApiError(deleteProject.error, 'The project could not be deleted.')}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" size="sm" onClick={submit} disabled={!canDelete}>
            {deleteProject.isPending ? 'Deleting…' : 'Delete project'}
          </Button>
        </div>
      </div>
    </div>
  )
}
