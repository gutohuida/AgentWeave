import { Button } from '@/components/ui/button'
import { Icon } from '@/components/common/Icon'
import type { RepositoryPreview } from '@/api/projects'

/** The anchor the set-up list links to (`a-project-says-what-it-needs`). */
export const MAKE_REPOSITORY_ANCHOR = 'make-repository'

/**
 * 'Make this a git repository', for a project folder that is not one
 * (`a-new-project-starts-as-a-git-repository-with-an-agents-md`, FR-6). Two steps: the first only
 * reads the list of what the first commit would hold; nothing is created until the operator
 * confirms that list.
 */
export function MakeRepositoryOffer({
  started,
  preview,
  previewError,
  confirming,
  refusal,
  onStart,
  onCancel,
  onConfirm,
}: {
  /** The operator asked to see the list. */
  started: boolean
  /** The list, once read. */
  preview?: RepositoryPreview | null
  /** Why it could not be read. */
  previewError?: string | null
  confirming?: boolean
  /** Why the confirm was refused. */
  refusal?: string | null
  onStart: () => void
  onCancel: () => void
  onConfirm: (files: string[]) => void
}) {
  if (!started) {
    return (
      <div id={MAKE_REPOSITORY_ANCHOR} className="flex flex-col gap-2" data-testid="make-repository-offer">
        <p className="aw-row-note">
          Without git, agents cannot each work in their own checkout, and approved work has nowhere to merge.
        </p>
        <span>
          <Button variant="outline" size="sm" onClick={onStart}>
            <Icon name="file_vcs" size={13} /> Make this a git repository…
          </Button>
        </span>
      </div>
    )
  }
  const count = preview?.files.length ?? 0
  return (
    <div id={MAKE_REPOSITORY_ANCHOR} className="flex flex-col gap-2" data-testid="make-repository-preview">
      {previewError ? (
        <p className="aw-row-note" data-tone="error">The folder could not be read: {previewError}</p>
      ) : !preview ? (
        <p className="aw-row-note">Reading the folder…</p>
      ) : (
        <>
          <p className="aw-row-note">
            The first commit would hold {count === 1 ? '1 file' : `${count} files`}
            {preview.agents_md ? ', plus a new AGENTS.md with AgentWeave’s guidance' : ''}. Files the repository will ignore are left out. Nothing is created until you confirm.
          </p>
          <ul
            className="aw-commit-files"
            aria-label="Files the first commit would hold"
          >
            {preview.agents_md ? <li>AGENTS.md (new)</li> : null}
            {preview.files.map((file) => (
              <li key={file}>{file}</li>
            ))}
          </ul>
        </>
      )}
      {refusal ? <p className="aw-row-note" data-tone="error">Not made a repository: {refusal}</p> : null}
      <span className="flex items-center gap-2">
        <Button size="sm" disabled={!preview || confirming} onClick={() => preview && onConfirm(preview.files)}>
          {confirming ? 'Making the repository…' : 'Make the repository and first commit'}
        </Button>
        <Button variant="outline" size="sm" disabled={confirming} onClick={onCancel}>
          Cancel
        </Button>
      </span>
    </div>
  )
}
