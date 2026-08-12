import { useEffect, useMemo, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { useCreateProject, useOpenProject, type ProjectSummary } from '@/api/projects'
import { useNativeDialogAvailability, useOpenNativeDialog } from '@/api/nativeDialog'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { Button } from '@/components/ui/button'
import { joinProjectPath, projectNameProblem } from '@/lib/projectTarget'
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
  // Create mode only: the new folder's name, which is also the project's name.
  const [projectName, setProjectName] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [nativeDialogNotice, setNativeDialogNotice] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const openProject = useOpenProject()
  const createProject = useCreateProject()
  const mutation = mode === 'create' ? createProject : openProject
  const { data: nativeAvailability } = useNativeDialogAvailability()
  const nativeDialog = useOpenNativeDialog()

  useEffect(() => {
    if (mode) {
      setPath('')
      setName('')
      setProjectName('')
      setPickerOpen(false)
      setNativeDialogNotice(null)
      openProject.reset()
      createProject.reset()
    }
    // Mutation objects are deliberately excluded; their identity changes as state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // Cancel leaves the typed path untouched and shows no error (task 8.2) — only
  // timeout/failure get a status of their own (task 8.3); "unavailable" shouldn't occur
  // here since the button offering this is itself gated on availability, but is handled
  // in its own terms rather than folded into "failed" in case availability changes
  // between the check and the click.
  const openNativeFolderDialog = () => {
    setNativeDialogNotice(null)
    nativeDialog.mutate(undefined, {
      onSuccess: (result) => {
        if (result.outcome === 'chosen' && result.path) {
          setPath(result.path)
        } else if (result.outcome === 'timeout') {
          setNativeDialogNotice('The folder dialog did not respond in time.')
        } else if (result.outcome === 'unavailable') {
          setNativeDialogNotice(result.detail ?? 'The native folder dialog is unavailable.')
        } else if (result.outcome === 'failed') {
          setNativeDialogNotice(result.detail ?? 'The folder dialog could not be opened.')
        }
      },
      onError: () => setNativeDialogNotice('The folder dialog could not be opened.'),
    })
  }

  useDialogFocus(!!mode, panelRef, onClose)

  const isCreate = mode === 'create'

  // In create mode the submitted path is composed here, and the preview below is derived
  // from this same value — never assembled alongside it. A preview that can disagree with
  // the payload is worse than no preview, because it is trusted.
  const target = useMemo(
    () => (isCreate ? joinProjectPath(path, projectName) : path.trim()),
    [isCreate, path, projectName],
  )
  const nameProblem = useMemo(
    () => (isCreate && projectName.trim() ? projectNameProblem(projectName) : null),
    [isCreate, projectName],
  )
  const preview = useMemo(() => {
    if (target) return target
    return isCreate
      ? 'Choose a folder to create the project in, then name it'
      : 'Enter an absolute local directory path'
  }, [target, isCreate])

  const canSubmit = isCreate
    ? Boolean(path.trim()) && projectNameProblem(projectName) === null
    : Boolean(path.trim())

  if (!mode) return null

  const submit = () => {
    if (!canSubmit || !target) return
    mutation.mutate(
      // Create sends no name: the backend already takes the project's name from the folder
      // it creates, which is exactly the behaviour being made visible here.
      isCreate ? { path: target } : { path: target, ...(name.trim() ? { name: name.trim() } : {}) },
      { onSuccess: onComplete },
    )
  }
  const error = mutation.error

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'var(--scrim)' }} role="dialog" aria-modal="true" aria-labelledby="project-manager-title">
      <div ref={panelRef} className="lifted-surface w-[min(520px,calc(100vw-32px))] p-5" style={{ background: 'var(--surface)' }}>
        <h2 id="project-manager-title" className="text-sm font-semibold">{mode === 'create' ? 'Create new project' : 'Open existing project'}</h2>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-3)' }}>
          {isCreate ? 'A new folder is created for the project, so the name must not already be taken.' : 'The directory must already exist.'}
          {' '}The path must be visible to the Hub process — when the Hub runs in Docker, it must lie beneath the configured mounted workspace root.
        </p>
        <label className="mt-4 block text-xs">
          {isCreate ? 'Create it in' : 'Directory path'}
          <div className="relative mt-1 flex gap-1.5">
            <input autoFocus value={path} onChange={(event) => setPath(event.target.value)} className="block w-full min-w-0 rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
            {nativeAvailability?.available ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={openNativeFolderDialog}
                disabled={nativeDialog.isPending}
                aria-label="Choose a folder"
              >
                {nativeDialog.isPending ? 'Waiting…' : 'Browse…'}
              </Button>
            ) : (
              <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen((v) => !v)} aria-expanded={pickerOpen} aria-label="Open directory browser">
                Browse…
              </Button>
            )}
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
        {nativeAvailability?.available && (
          // The in-app browser stays reachable even when the native dialog is offered
          // (design.md Decision 4: "The in-app browser is not deleted").
          <button
            type="button"
            className="mt-1 text-[11px] underline"
            style={{ color: 'var(--text-3)' }}
            onClick={() => setPickerOpen((v) => !v)}
            aria-expanded={pickerOpen}
          >
            {pickerOpen ? 'Hide the in-Hub browser' : 'Browse within the Hub instead'}
          </button>
        )}
        {nativeDialogNotice && (
          <p role="status" className="mt-1 text-[11px]" style={{ color: 'var(--amber)' }}>
            {nativeDialogNotice}
          </p>
        )}
        {isCreate && (
          <label className="mt-3 block text-xs">
            Project name
            <input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              aria-label="Project name"
              aria-invalid={nameProblem ? true : undefined}
              placeholder="my-project"
              className="mt-1 block w-full rounded px-3 py-2"
              style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}
            />
            <span className="mt-1 block text-[11px]" style={{ color: 'var(--text-3)' }}>
              This names the new folder and the project.
            </span>
          </label>
        )}
        {nameProblem && (
          <p role="alert" className="mt-1 text-[11px]" style={{ color: 'var(--red)' }}>
            {nameProblem}
          </p>
        )}
        <div data-testid="project-path-preview" className="mt-2 truncate rounded px-3 py-2 text-xs" style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>{preview}</div>
        {!isCreate && (
          <label className="mt-3 block text-xs">
            Display name <span style={{ color: 'var(--text-3)' }}>(optional)</span>
            <input value={name} onChange={(event) => setName(event.target.value)} aria-label="Display name" className="mt-1 block w-full rounded px-3 py-2" style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }} />
          </label>
        )}
        {error && (
          <div role="alert" className="mt-3 rounded px-3 py-2 text-xs" style={{ background: 'var(--error-cont)', color: 'var(--red)' }}>
            {error instanceof ApiError ? error.message : 'The project could not be registered.'}
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="button" onClick={submit} disabled={!canSubmit || mutation.isPending} data-testid="confirm-project-action">
            {mutation.isPending ? 'Workingâ€¦' : mode === 'create' ? 'Create project' : 'Open project'}
          </button>
        </div>
      </div>
    </div>
  )
}
