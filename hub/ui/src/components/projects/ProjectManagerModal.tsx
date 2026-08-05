import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { useCreateProject, useOpenProject, type ProjectSummary } from '@/api/projects'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { Button } from '@/components/ui/button'
import { DirectoryPicker } from './DirectoryPicker'

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
  const [pickerOpen, setPickerOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const openProject = useOpenProject()
  const createProject = useCreateProject()
  const mutation = mode === 'create' ? createProject : openProject

  useEffect(() => {
    if (mode) {
      setPath('')
      setName('')
      setPickerOpen(false)
      openProject.reset()
      createProject.reset()
    }
    // Mutation objects are deliberately excluded; their identity changes as state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  useDialogFocus(!!mode, panelRef, onClose)

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
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'var(--scrim)' }} role="dialog" aria-modal="true" aria-labelledby="project-manager-title">
      <div ref={panelRef} className="lifted-surface w-[min(520px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="project-manager-title" className="text-sm font-semibold">{mode === 'create' ? 'Create new project' : 'Open existing project'}</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {mode === 'create' ? 'The target must not already contain project files.' : 'The directory must already exist.'}
          {' '}The path must be visible to the Hub process — when the Hub runs in Docker, it must lie beneath the configured mounted workspace root.
        </p>
        <label className="mt-4 block text-xs">
          Directory path
          <div className="relative mt-1 flex gap-1.5">
            <input autoFocus value={path} onChange={(event) => setPath(event.target.value)} className="block w-full min-w-0 rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
            <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen((v) => !v)} aria-expanded={pickerOpen} aria-label="Open directory browser">
              Browse…
            </Button>
            {pickerOpen && (
              <DirectoryPicker
                startPath={/^([a-zA-Z]:[\\/]|\/)/.test(path.trim()) ? path.trim() : '/'}
                onChoose={(chosen) => {
                  setPath(chosen)
                  setPickerOpen(false)
                }}
                onClose={() => setPickerOpen(false)}
              />
            )}
          </div>
        </label>
        <div data-testid="project-path-preview" className="mt-2 truncate rounded px-3 py-2 text-xs" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>{preview}</div>
        <label className="mt-3 block text-xs">
          Display name <span style={{ color: 'var(--text-3)' }}>(optional)</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 block w-full rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
        </label>
        {error && (
          <div role="alert" className="mt-3 rounded px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--red)' }}>
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
