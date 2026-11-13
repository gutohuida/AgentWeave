import * as React from 'react'
import type { ChangePatch, ChangedFile, ChangesScope, ConversationChanges } from '@/api/changes'
import { DiffView } from '@/components/common/DiffView'
import { Icon } from '@/components/common/Icon'
import { Segmented } from '@/components/ui/segmented'
import '@/styles/story.css'
import '@/styles/panel-tabs.css'

export type { ChangesScope }

/** The selected file's diff as the Hub answered it, while it loads, or when it could not be read. */
export type PatchState = { status: 'loading' } | { status: 'failed' } | { status: 'ready'; patch: ChangePatch }

export interface ChangesTabProps {
  agent: string
  /** The Hub's answer for the conversation; `undefined` while the first one loads. */
  data: ConversationChanges | undefined
  loadFailed?: boolean
  scope: ChangesScope
  onScopeChange: (scope: ChangesScope) => void
  /** The file whose diff is shown below the list, and that diff. */
  selected: string | null
  onSelect: (path: string) => void
  patch: PatchState | null
  /** Opens the file, as it is in the agent's worktree, in the Files tab. */
  onOpenFile: (path: string) => void
}

function Notice({ icon, children }: { icon: string; children: React.ReactNode }) {
  return (
    <div className="aw-ptab-empty">
      <span className="aw-ptab-empty-icon">
        <Icon name={icon} size={18} />
      </span>
      <p>{children}</p>
    </div>
  )
}

function taskName(task: NonNullable<ConversationChanges['task']>): string {
  return [task.readable_id, task.title].filter(Boolean).join(' — ') || task.id
}

/** The side panel's Changes tab: what the conversation's agent changed, file by file, as diffs. */
export function ChangesTab({ agent, data, loadFailed, scope, onScopeChange, selected, onSelect, patch, onOpenFile }: ChangesTabProps) {
  if (!data) {
    return (
      <div className="aw-ptab" data-testid="changes-tab">
        <div className="aw-ptab-scroll">
          {loadFailed ? (
            <Notice icon="info">{agent}’s changes could not be loaded just now.</Notice>
          ) : (
            <p className="aw-ptab-note">Loading changes…</p>
          )}
        </div>
      </div>
    )
  }
  if (data.state === 'no_checkout' || data.state === 'unreadable') {
    return (
      <div className="aw-ptab" data-testid="changes-tab">
        <div className="aw-ptab-scroll">
          <Notice icon="info">
            {data.message ||
              (data.state === 'no_checkout' ? `${agent} has no checkout of its own.` : `${agent}’s branch cannot be read.`)}
          </Notice>
        </div>
      </div>
    )
  }

  const base = data.base ?? 'main'
  const branch = data.branch ?? ''
  const files: ChangedFile[] = scope === 'turn' ? data.turn : data.since_base
  const [added, removed] = files.reduce(([a, r], f) => [a + f.added, r + f.removed], [0, 0])
  const shown = files.find((f) => f.path === selected) ?? null

  return (
    <div className="aw-ptab" data-testid="changes-tab">
      <div className="aw-ptab-head">
        <div className="aw-ptab-title-row">
          <span className="aw-ptab-title">{agent}’s changes</span>
          <span className="aw-ptab-branch" title={`${branch}, compared with ${base}`}>
            <Icon name="call_split" size={12} />
            {branch}
          </span>
        </div>
        {data.task ? (
          <p className="aw-ptab-note" data-testid="changes-task">
            Working on {taskName(data.task)}
          </p>
        ) : null}
        <div className="aw-ptab-controls">
          <Segmented<ChangesScope>
            label="Changes since"
            size="xs"
            value={scope}
            onChange={onScopeChange}
            options={[
              { value: 'turn', label: 'Last turn', count: data.turn.length || undefined },
              { value: 'branch', label: `Since ${base}`, count: data.since_base.length || undefined },
            ]}
          />
          {files.length > 0 ? (
            <span className="aw-ptab-stat">
              {files.length} {files.length === 1 ? 'file' : 'files'}
              <span className="add">+{added}</span>
              <span className="del">−{removed}</span>
            </span>
          ) : null}
        </div>
      </div>
      <div className="aw-ptab-scroll">
        {data.working_now.length > 0 ? (
          <p className="aw-ptab-note" data-testid="changes-working-now">
            Working now: {data.working_now.join(', ')}
          </p>
        ) : null}
        {files.length === 0 ? (
          data.state === 'empty' ? (
            <Notice icon="check_circle">{agent} has changed nothing yet.</Notice>
          ) : (
            <Notice icon="check_circle">
              {scope === 'turn' ? `${agent}’s last turn changed no files.` : `Nothing on ${branch} differs from ${base}.`}
            </Notice>
          )
        ) : (
          <>
            <ul className="aw-changes-files" aria-label="Changed files">
              {files.map((f) => {
                const name = f.path.slice(f.path.lastIndexOf('/') + 1)
                const dir = f.path.slice(0, Math.max(0, f.path.lastIndexOf('/')))
                return (
                  <li key={f.path} style={{ display: 'flex', alignItems: 'center' }}>
                    <button
                      type="button"
                      data-slot="changes-file"
                      className="aw-changes-file"
                      style={{ flex: 1, minWidth: 0 }}
                      aria-pressed={f.path === selected}
                      onClick={() => onSelect(f.path)}
                    >
                      <span className="aw-changes-letter" data-status={f.status}>
                        {f.status}
                      </span>
                      <span className="aw-changes-name">{name}</span>
                      <span className="aw-changes-dir">{dir}</span>
                      <span className="aw-changes-stat">
                        <span className="add">+{f.added}</span>
                        <span className="del">−{f.removed}</span>
                      </span>
                    </button>
                    {f.status !== 'D' ? (
                      <button
                        type="button"
                        data-slot="changes-open-file"
                        className="aw-changes-file"
                        style={{ flex: 'none', width: 28, justifyContent: 'center' }}
                        onClick={() => onOpenFile(f.path)}
                        aria-label={`Open ${f.path} in Files`}
                        title={`Open ${f.path} in Files`}
                      >
                        <Icon name="folder_open" size={13} />
                      </button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
            {shown ? <SelectedDiff file={shown} patch={patch} /> : <p className="aw-ptab-note">Select a file to see its diff.</p>}
          </>
        )}
      </div>
    </div>
  )
}

function SelectedDiff({ file, patch }: { file: ChangedFile; patch: PatchState | null }) {
  if (!patch || patch.status === 'loading') return <p className="aw-ptab-note">Loading the diff…</p>
  if (patch.status === 'failed') return <p className="aw-ptab-note">{file.path}’s diff could not be read.</p>
  const { patch: result } = patch
  if (result.binary) return <p className="aw-ptab-note" data-testid="changes-binary">{file.path} is a binary file: there is no diff to show.</p>
  return (
    <>
      {result.truncated ? (
        <p className="aw-ptab-note" data-testid="changes-truncated">
          This diff is too long to show whole ({result.total_lines.toLocaleString()} lines): its start is shown.
        </p>
      ) : null}
      <DiffView key={`${file.path}:${result.truncated}`} files={[{ path: file.path, status: file.status, patch: result.patch }]} testId="changes-diff" />
    </>
  )
}
