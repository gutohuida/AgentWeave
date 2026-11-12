import * as React from 'react'
import { DiffView, type DiffFile } from '@/components/common/DiffView'
import { Icon } from '@/components/common/Icon'
import { Segmented } from '@/components/ui/segmented'
import { diffStat } from '@/lib/diffLines'
import '@/styles/story.css'
import '@/styles/panel-tabs.css'

export type ChangesScope = 'turn' | 'branch'

export interface ChangesTabProps {
  agent: string
  branch: string
  base: string
  /** What the agent's last turn changed, and everything on its branch since it left `base`. */
  turn: DiffFile[]
  wholeBranch: DiffFile[]
  /** Opens the file, as it is in the agent's worktree, in the Files tab. */
  onOpenFile: (path: string) => void
}

/** The side panel's Changes tab: what the conversation's agent changed, file by file, as diffs. */
export function ChangesTab({ agent, branch, base, turn, wholeBranch, onOpenFile }: ChangesTabProps) {
  const [scope, setScope] = React.useState<ChangesScope>('turn')
  const files = scope === 'turn' ? turn : wholeBranch
  const [added, removed] = files.reduce(([a, r], f) => {
    const [fa, fr] = diffStat(f.patch)
    return [a + fa, r + fr]
  }, [0, 0])

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
        <div className="aw-ptab-controls">
          <Segmented<ChangesScope>
            label="Changes since"
            size="xs"
            value={scope}
            onChange={setScope}
            options={[
              { value: 'turn', label: 'Last turn', count: turn.length || undefined },
              { value: 'branch', label: `Since ${base}`, count: wholeBranch.length || undefined },
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
        {files.length === 0 ? (
          <div className="aw-ptab-empty">
            <span className="aw-ptab-empty-icon">
              <Icon name="check_circle" size={18} />
            </span>
            <p>{scope === 'turn' ? `${agent}’s last turn changed no files.` : `Nothing on ${branch} differs from ${base}.`}</p>
          </div>
        ) : (
          <>
            <ul className="aw-changes-files" aria-label="Changed files">
              {files.map((f) => {
                const [a, r] = diffStat(f.patch)
                const name = f.path.slice(f.path.lastIndexOf('/') + 1)
                const dir = f.path.slice(0, Math.max(0, f.path.lastIndexOf('/')))
                return (
                  <li key={f.path}>
                    <button type="button" data-slot="changes-file" className="aw-changes-file" onClick={() => onOpenFile(f.path)} title={`Open ${f.path}`}>
                      <span className="aw-changes-letter" data-status={f.status}>
                        {f.status}
                      </span>
                      <span className="aw-changes-name">{name}</span>
                      <span className="aw-changes-dir">{dir}</span>
                      <span className="aw-changes-stat">
                        <span className="add">+{a}</span>
                        <span className="del">−{r}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <DiffView key={scope} files={files} testId="changes-diff" />
          </>
        )}
      </div>
    </div>
  )
}
