import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '@/api/client'
import { useCreateProject, useOpenProject, type ProjectSummary } from '@/api/projects'

export type ProjectManagerMode = 'open' | 'create'

export function ProjectManagerModal({
  mode,
  onClose,
  onComplete,
}: {
  mode: ProjectManagerMode | null
  onClose: () => void
  onComplete: (project: ProjectSummary) => void
}) {
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  const openProject = useOpenProject()
  const createProject = useCreateProject()
  const mutation = mode === 'create' ? createProject : openProject

  useEffect(() => {
    if (mode) {
      setPath('')
      setName('')
      openProject.reset()
      createProject.reset()
    }
    // Mutation objects are deliberately excluded; their identity changes as state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const preview = useMemo(() => path.trim() || 'Enter an absolute local directory path', [path])
  if (!mode) return null

  const submit = () => {
    const target = path.trim()
    if (!target) return
    mutation.mutate(
      { path: target, ...(name.trim() ? { name: name.trim() } : {}) },
      { onSuccess: onComplete },
    )
  }
  const error = mutation.error

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgb(0 0 0 / 0.45)' }} role="dialog" aria-modal="true" aria-labelledby="project-manager-title">
      <div className="w-[min(520px,calc(100vw-32px))] rounded-lg p-5" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
        <h2 id="project-manager-title" className="text-sm font-semibold">{mode === 'create' ? 'Create new project' : 'Open existing project'}</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {mode === 'create' ? 'The target must not already contain project files.' : 'The directory must already exist.'}
          {' '}The path must be visible to the Hub process — when the Hub runs in Docker, it must lie beneath the configured mounted workspace root.
        </p>
        <label className="mt-4 block text-xs">
          Directory path
          <input autoFocus value={path} onChange={(event) => setPath(event.target.value)} className="mt-1 block w-full rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
        </label>
        <div data-testid="project-path-preview" className="mt-2 truncate rounded px-3 py-2 text-xs" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>{preview}</div>
        <label className="mt-3 block text-xs">
          Display name <span style={{ color: 'var(--text-3)' }}>(optional)</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 block w-full rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
        </label>
        {error && (
          <div role="alert" className="mt-3 rounded px-3 py-2 text-xs" style={{ background: 'var(--danger-bg)', color: 'var(--red)' }}>
            {error instanceof ApiError ? error.message : 'The project could not be registered.'}
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" onClick={submit} disabled={!path.trim() || mutation.isPending} data-testid="confirm-project-action">
            {mutation.isPending ? 'Workingâ€¦' : mode === 'create' ? 'Create project' : 'Open project'}
          </button>
        </div>
      </div>
    </div>
  )
}
