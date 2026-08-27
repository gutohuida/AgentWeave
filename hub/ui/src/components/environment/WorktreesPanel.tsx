import { SettingsSection } from '@/components/environment/SettingsSection'
import { EmptyState } from '@/components/common/EmptyState'
import { useWorktrees, type WorkspaceInfo } from '@/api/workspace'

/**
 * Every Hub-owned checkout in this project, agent and task alike.
 *
 * **Task 6.4b, and the decision it asked for.** This panel was a stub: a hard-coded "No worktree
 * activity" that called no API and so said the same thing whether the project had no checkouts or
 * a dozen. The choice was to point it at `GET /worktrees` or to say in its own copy that it is not
 * implemented, and pointing it at the endpoint is the honest one — since task 6.3 that endpoint
 * returns exactly what this panel claims to show, kind included, so the alternative would have
 * been a message apologising for a stub that had a working data source sitting next to it.
 *
 * Grouped by kind rather than listed flat, because the two answer different questions: an agent
 * checkout is where an agent works between tasks, and a task checkout is where one piece of work
 * happens no matter who picks it up. Reading this provisions nothing, so an empty list now means
 * the project genuinely has no checkouts.
 */
export function WorktreesPanel() {
  const { data, isLoading, error } = useWorktrees()

  return (
    <SettingsSection
      title="Worktrees"
      description="The isolated checkouts this project is using — one per writing agent, and one per task being worked."
    >
      <PanelBody data={data} isLoading={isLoading} error={error} />
    </SettingsSection>
  )
}

function PanelBody({
  data,
  isLoading,
  error,
}: {
  data: WorkspaceInfo[] | undefined
  isLoading: boolean
  error: unknown
}) {
  // Distinguished from "no checkouts" deliberately: this panel's whole defect was saying "nothing
  // here" when it did not know. A failed read is not an empty project.
  if (error) {
    return (
      <div className="py-4 text-xs" style={{ color: 'var(--amber)' }} role="alert">
        Could not read this project's checkouts.
      </div>
    )
  }

  // `!data` covers more than the fetch in flight: with no project selected the query is disabled
  // and never resolves, so there is no answer rather than an empty one. Both are "nothing to say
  // yet", and neither is a failure — reporting either as an error would be the same lie in the
  // other direction.
  if (isLoading || !data) {
    return (
      <div className="space-y-2 py-4" aria-label="Loading worktrees">
        {[0, 1].map((row) => <div key={row} className="skeleton h-12 w-full" />)}
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="py-4">
        <EmptyState
          icon="file_vcs"
          title="No worktree activity"
          description="Isolated checkouts appear here when an agent starts work that needs one, and when a task is picked up."
        />
      </div>
    )
  }

  const agents = data.filter((workspace) => workspace.kind === 'agent')
  const tasks = data.filter((workspace) => workspace.kind === 'task')
  // Anything the Hub reports under a kind this build does not know about is still shown rather
  // than dropped: a checkout that exists and is not listed is the failure this panel is fixing.
  const others = data.filter((workspace) => workspace.kind !== 'agent' && workspace.kind !== 'task')

  return (
    <div className="space-y-5 py-2" data-testid="worktrees-list">
      <WorkspaceGroup
        heading="Agent checkouts"
        note="Where an agent works when its turn is not bound to a task."
        workspaces={agents}
      />
      <WorkspaceGroup
        heading="Task checkouts"
        note="One per task being worked. Released when the task is approved or rejected; the branch is kept."
        workspaces={tasks}
      />
      <WorkspaceGroup heading="Other checkouts" workspaces={others} />
    </div>
  )
}

function WorkspaceGroup({
  heading,
  note,
  workspaces,
}: {
  heading: string
  note?: string
  workspaces: WorkspaceInfo[]
}) {
  if (workspaces.length === 0) return null

  return (
    <div>
      <h4 className="text-xs font-medium" style={{ color: 'var(--text-2)' }}>{heading}</h4>
      {note && (
        <p className="mt-0.5 text-[11px]" style={{ color: 'var(--text-3)' }}>{note}</p>
      )}
      <ul className="mt-2 space-y-2">
        {workspaces.map((workspace) => (
          <li key={`${workspace.kind}:${workspace.name}`} data-testid={`worktree-${workspace.name}`}>
            <div className="text-sm" style={{ color: 'var(--text)' }}>{workspace.name}</div>
            <code
              className="mt-1 block truncate text-[11px]"
              style={{
                background: 'var(--surface-2)',
                color: 'var(--text-2)',
                padding: '3px 6px',
                borderRadius: '4px',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {workspace.path}
            </code>
            <p className="mt-1 text-[11px]" style={{ color: 'var(--text-3)' }}>{workspace.branch}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
