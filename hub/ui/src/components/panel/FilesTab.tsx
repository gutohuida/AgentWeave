import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { fileColourFor, fileIconFor } from '@/components/spec/fileIcons'
import { buildFilePathTree } from '@/components/spec/specNavigation'
import { LocationSwitch, type PanelLocation } from './LocationSwitch'
import '@/styles/panel-tabs.css'

/** git's name-status letter for a file the agent changed: added, modified, deleted. */
export type ChangeMark = 'A' | 'M' | 'D'

export interface FilesTabProps {
  agent: string
  location: PanelLocation
  onLocationChange: (next: PanelLocation) => void
  paths: readonly string[]
  /** Files the agent changed on its branch, marked in its worktree's tree. Empty for the root. */
  changed: Readonly<Record<string, ChangeMark>>
  currentPath: string | null
  onOpen: (path: string) => void
}

const MARK_WORD: Record<ChangeMark, string> = { A: 'Added', M: 'Modified', D: 'Deleted' }

/** The side panel's Files tab: the agent's worktree or the project root, as a tree, with the
 *  agent's changes marked and a switch to see only those. */
export function FilesTab({ agent, location, onLocationChange, paths, changed, currentPath, onOpen }: FilesTabProps) {
  const [query, setQuery] = React.useState('')
  const [changedOnly, setChangedOnly] = React.useState(false)
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({})
  const changeCount = Object.keys(changed).length
  // A file the agent deleted is gone from its worktree, but stays in the tree, struck through.
  const all = location === 'worktree' ? [...paths, ...Object.keys(changed).filter((p) => changed[p] === 'D' && !paths.includes(p))] : paths
  const scoped = location === 'worktree' && changedOnly ? all.filter((p) => changed[p]) : all
  const typed = query.trim().toLowerCase()
  const matches = typed ? scoped.filter((p) => p.toLowerCase().includes(typed)) : null
  const rows = React.useMemo(() => buildFilePathTree(scoped), [scoped])
  const hidden = (path: string) => Object.entries(collapsed).some(([dir, c]) => c && path.startsWith(`${dir}/`))
  const mark = (path: string) => (location === 'worktree' ? changed[path] : undefined)
  // A folder holding a change carries a quiet dot, so a change deep in a collapsed folder is not lost.
  const dirChanged = (dir: string) => location === 'worktree' && Object.keys(changed).some((p) => p.startsWith(`${dir}/`))

  const fileRow = (path: string, label: string, depth: number, showDir: boolean) => {
    const m = mark(path)
    return (
      <button
        key={`file:${path}`}
        type="button"
        data-slot="files-row"
        className="aw-files-row"
        data-active={path === currentPath ? 'true' : undefined}
        style={{ paddingLeft: 10 + depth * 14 + 18 }}
        onClick={() => onOpen(path)}
        title={m ? `${path} — ${MARK_WORD[m].toLowerCase()} by ${agent}` : path}
      >
        <Icon name={fileIconFor(path)} size={14} style={{ color: fileColourFor(path), flexShrink: 0 }} />
        <span className="aw-files-name" data-deleted={m === 'D' ? 'true' : undefined}>
          {label}
        </span>
        {showDir ? <span className="aw-files-dir">{path.slice(0, path.length - label.length)}</span> : null}
        {m ? (
          <span className="aw-changes-letter" data-status={m} aria-label={MARK_WORD[m]}>
            {m}
          </span>
        ) : null}
      </button>
    )
  }

  return (
    <div className="aw-ptab" data-testid="files-tab">
      <div className="aw-ptab-head">
        <div className="aw-ptab-controls">
          <LocationSwitch agent={agent} value={location} onChange={onLocationChange} />
          {location === 'worktree' && changeCount > 0 ? (
            <label className="aw-files-changed-only">
              <Switch checked={changedOnly} onCheckedChange={setChangedOnly} aria-label="Only files the agent changed" />
              Changed only
              <span className="aw-ptab-count">{changeCount}</span>
            </label>
          ) : null}
        </div>
        <div className="aw-ptab-search">
          <Icon name="search" size={14} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && setQuery('')} placeholder="Find a file" aria-label="Find a file" />
          {query ? (
            <Button variant="ghost" size="icon-xs" onClick={() => setQuery('')} aria-label="Clear">
              <Icon name="close" size={13} />
            </Button>
          ) : null}
        </div>
      </div>
      <div className="aw-ptab-scroll aw-files-list">
        {matches ? (
          matches.length === 0 ? (
            <p className="aw-ptab-note">No file matches “{query.trim()}”.</p>
          ) : (
            matches.map((p) => fileRow(p, p.slice(p.lastIndexOf('/') + 1), 0, true))
          )
        ) : rows.length === 0 ? (
          <p className="aw-ptab-note">{changedOnly ? `${agent} has changed no files.` : 'No files here yet.'}</p>
        ) : (
          rows
            .filter((row) => !hidden(row.path))
            .map((row) =>
              row.kind === 'directory' ? (
                <button
                  key={`dir:${row.path}`}
                  type="button"
                  data-slot="files-dir"
                  className="aw-files-row aw-files-folder"
                  aria-expanded={!collapsed[row.path]}
                  style={{ paddingLeft: 10 + row.depth * 14 }}
                  onClick={() => setCollapsed((c) => ({ ...c, [row.path]: !c[row.path] }))}
                >
                  <span className="aw-files-chevron" data-open={collapsed[row.path] ? undefined : 'true'}>
                    <Icon name="chevron_right" size={13} />
                  </span>
                  <Icon name={collapsed[row.path] ? 'folder' : 'folder_open'} size={14} />
                  <span className="aw-files-name">{row.label}</span>
                  {dirChanged(row.path) ? <span className="aw-files-dot" aria-label="Holds changes" /> : null}
                </button>
              ) : (
                fileRow(row.path, row.label, row.depth, false)
              ),
            )
        )}
      </div>
    </div>
  )
}
