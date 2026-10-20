import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { SettingsGroup, SettingsLoading, SettingsPage } from '@/components/ui/settings'
import type { ConflictWorkspace, WorkspaceInfo, WorktreeConflict, WorktreeListing } from '@/api/workspace'
import { formatCount } from '@/lib/format'

/** Project settings → Instructions, Worktrees and Diagnostics. */

/** Instructions are a text body, so they are the one place with a Save button: enabled only when
 *  the text differs from what is stored, with "Unsaved changes" beside it. */
export function InstructionsSettings({
  content,
  maxChars,
  onSave,
  saving,
  justSaved,
  notices,
}: {
  content: string
  /** The Hub's limit; unknown (an older Hub) shows no count and refuses nothing here. */
  maxChars?: number
  onSave: (content: string) => void
  saving?: boolean
  /** The last save landed a moment ago: "Saved" shows where "Unsaved changes" was. */
  justSaved?: boolean
  /** A refused save, under the page heading. */
  notices?: React.ReactNode
}) {
  const [draft, setDraft] = React.useState(content)
  React.useEffect(() => setDraft(content), [content])
  const dirty = draft !== content
  const over = maxChars !== undefined && draft.length > maxChars
  return (
    <SettingsPage
      icon="description"
      title="Instructions"
      description="Rules every agent in this project reads at the start of a session, before its own charter."
      actions={
        <>
          {dirty ? (
            <span className="aw-unsaved">Unsaved changes</span>
          ) : justSaved ? (
            <span className="aw-saved" role="status">
              <Icon name="check" size={13} /> Saved
            </span>
          ) : null}
          <Button variant="ghost" size="sm" disabled={!dirty} onClick={() => setDraft(content)}>
            Discard
          </Button>
          <Button variant="primary" size="sm" disabled={!dirty || over || saving} onClick={() => onSave(draft)}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
      {notices}
      <div className="aw-instructions">
        <Textarea
          aria-label="Project instructions"
          className="aw-instructions-field"
          value={draft}
          placeholder={'For example:\n- Run the tests before you say a task is done.\n- Never push to master; the Hub merges approved work.'}
          spellCheck={false}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="aw-instructions-foot" data-testid="instructions-size" role={over ? 'alert' : undefined}>
          <span>
            {over
              ? 'Too long to save: these are sent with every agent turn, so shorten them or point to reference material in the project instead.'
              : 'Sent with every agent turn, so each character is paid for on each one. New sessions pick up a change; running ones keep what they started with.'}
          </span>
          {maxChars !== undefined ? (
            <span className="tabular" data-over={over ? 'true' : 'false'}>
              {formatCount(draft.length)} / {formatCount(maxChars)}
            </span>
          ) : null}
        </div>
      </div>
    </SettingsPage>
  )
}

function WorktreesEmpty({ title, description, testId }: { title: string; description: string; testId?: string }) {
  return (
    <div className="aw-settings-empty" data-testid={testId}>
      <span className="aw-settings-empty-icon">
        <Icon name="call_split" size={18} />
      </span>
      <p className="aw-settings-empty-title">{title}</p>
      <p className="aw-settings-empty-desc">{description}</p>
    </div>
  )
}

function describeWorkspace(workspace: ConflictWorkspace): string {
  if (workspace.kind === 'agent') return `agent ${workspace.name}`
  if (workspace.kind === 'task') return `task ${workspace.name}`
  if (workspace.kind === 'main') return `the main branch (${workspace.branch})`
  return `${workspace.kind} ${workspace.name}`
}

/** Every Hub-owned checkout in the project, by kind, and what git says would not merge.
 *
 *  A failed read is not an empty project, and an unanswered one is neither (F249, F250): each says
 *  so. A checkout of a kind this build does not know is still listed. Conflicts are shown even with
 *  no checkout listed, since a finished task's branch can outlive its checkout (F246). */
export function WorktreesSettings({
  listing,
  error,
  conflicts,
  conflictsError,
}: {
  /** Undefined while the Hub has not answered (or no project is selected). */
  listing: WorktreeListing | undefined
  error?: boolean
  /** Undefined while the conflict check is running. */
  conflicts?: WorktreeConflict[]
  conflictsError?: boolean
}) {
  let body: React.ReactNode
  if (error) {
    body = (
      <p className="aw-inline-warning" role="alert">
        <Icon name="warning" size={13} /> Could not read this project's checkouts.
      </p>
    )
  } else if (!listing) {
    body = <SettingsLoading label="Loading worktrees" rows={2} />
  } else if (!listing.repository) {
    body = (
      <WorktreesEmpty
        testId="worktrees-not-a-repository"
        title="This folder is not a git repository"
        description={listing.unavailable_reason ?? 'Agents work in the folder itself, and approved work has nowhere to merge.'}
      />
    )
  } else if (listing.worktrees.length === 0) {
    body = <WorktreesEmpty title="No checkouts right now" description="One appears here when an agent starts work that needs its own copy, and when a task is picked up." />
  } else {
    const agents = listing.worktrees.filter((w) => w.kind === 'agent')
    const tasks = listing.worktrees.filter((w) => w.kind === 'task')
    const others = listing.worktrees.filter((w) => w.kind !== 'agent' && w.kind !== 'task')
    body = (
      <div data-testid="worktrees-list">
        <WorkspaceGroup title="Agent checkouts" note="Where an agent works when its turn is not bound to a task." workspaces={agents} />
        <WorkspaceGroup title="Task checkouts" note="One per task being worked. Released when the task is approved or rejected; the branch is kept." workspaces={tasks} />
        <WorkspaceGroup title="Other checkouts" workspaces={others} />
      </div>
    )
  }

  let conflictBody: React.ReactNode = null
  if (listing?.repository && !error) {
    if (conflictsError) {
      conflictBody = (
        <p className="aw-inline-warning" role="alert">
          <Icon name="warning" size={13} /> Could not check these checkouts for conflicts.
        </p>
      )
    } else if (conflicts && conflicts.length > 0) {
      conflictBody = (
        <div data-testid="worktree-conflicts">
        <SettingsGroup
          title={conflicts.length === 1 ? '1 conflict' : `${conflicts.length} conflicts`}
          description="Each pair would not merge cleanly: integrating one after the other stops on these files until the conflict is resolved."
        >
          <ul className="aw-list">
            {conflicts.map((conflict) => {
              const [a, b] = conflict.workspaces
              return (
                <li key={`${a.branch}|${b.branch}`} className="aw-list-row aw-list-row-tall">
                  <span className="aw-list-mark">
                    <Icon name="warning" size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="aw-list-title">
                      {describeWorkspace(a)} and {describeWorkspace(b)}
                    </span>
                    <span className="aw-list-sub">
                      {a.branch} · {b.branch}
                    </span>
                    <ul className="aw-conflict-files">
                      {conflict.paths.map((path) => (
                        <li key={path}>
                          <code className="aw-path">{path}</code>
                        </li>
                      ))}
                    </ul>
                  </span>
                </li>
              )
            })}
          </ul>
        </SettingsGroup>
        </div>
      )
    } else if (conflicts && listing.worktrees.length > 0) {
      conflictBody = (
        <p className="aw-empty-line" data-testid="worktree-conflicts-none">
          No conflicts: git finds nothing here that would stop a merge.
        </p>
      )
    }
  }

  return (
    <SettingsPage icon="call_split" title="Worktrees" description="The separate checkouts agents work in: one per writing agent, and one per task being worked.">
      {body}
      {conflictBody}
    </SettingsPage>
  )
}

function WorkspaceGroup({ title, note, workspaces }: { title: string; note?: string; workspaces: WorkspaceInfo[] }) {
  if (workspaces.length === 0) return null
  return (
    <SettingsGroup title={title} description={note}>
      <ul className="aw-list">
        {workspaces.map((workspace) => (
          <li key={`${workspace.kind}:${workspace.name}`} className="aw-list-row" data-testid={`worktree-${workspace.name}`}>
            <span className="aw-list-mark">
              <Icon name={workspace.kind === 'task' ? 'task_alt' : 'call_split'} size={15} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="aw-list-title">{workspace.name}</span>
              <code className="aw-path" title={workspace.path}>
                {workspace.path}
              </code>
            </span>
            <span className="aw-list-meta font-mono">{workspace.branch}</span>
          </li>
        ))}
      </ul>
    </SettingsGroup>
  )
}

export interface DiagnosticsLine {
  label: string
  value: React.ReactNode
}

export function DiagnosticsSettings({
  groups,
  rawStatus,
  onCopy,
}: {
  groups: Array<{ title: string; lines: DiagnosticsLine[] }>
  /** The Hub's status as text, for pasting into an issue. */
  rawStatus: string
  onCopy: (text: string) => void
}) {
  return (
    <SettingsPage
      icon="monitoring"
      title="Diagnostics"
      description="What the Hub reports about this project right now, for troubleshooting."
      actions={
        <Button variant="outline" size="sm" onClick={() => onCopy(rawStatus)}>
          <Icon name="content_copy" size={13} /> Copy status
        </Button>
      }
    >
      {groups.map((group) => (
        <SettingsGroup key={group.title} title={group.title}>
          <dl className="aw-kv">
            {group.lines.map((line) => (
              <div key={line.label} className="aw-kv-row">
                <dt>{line.label}</dt>
                <dd className="tabular">{line.value}</dd>
              </div>
            ))}
          </dl>
        </SettingsGroup>
      ))}
      <SettingsGroup title="Raw status" description="Exactly what the Hub answered, for an issue report.">
        <pre className="settings-code-surface aw-raw-status" tabIndex={0} aria-label="Raw Hub status">
          {rawStatus}
        </pre>
      </SettingsGroup>
    </SettingsPage>
  )
}
