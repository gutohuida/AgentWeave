import { useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { FileTree } from './FileTree'

interface FilesIndexTabProps {
  paths: readonly string[]
  isLoading: boolean
  /** The file open in a `file:` tab right now, if any — marked in the tree the same way the
   *  specs index tab marks the attached document. */
  currentPath: string | null
  onSelect: (path: string) => void
}

/**
 * The panel shell's `files` index tab (task 5.1, `2026-08-18-one-shell-three-panels`): a tree
 * built from `GET /api/v1/workspace/paths`, browsable and searchable the same way the specs
 * index tab is browsable and searchable — the tree for finding your way around, the flat ranked
 * list once you can name what you are looking for.
 *
 * Selecting a file opens it for reading only. Per design D8, opening it also closes this tab —
 * that happens in `panelTabsStore.openTab`, not here, so every caller of `openTab` gets the same
 * rule rather than each call site remembering to apply it.
 */
export function FilesIndexTab({ paths, isLoading, currentPath, onSelect }: FilesIndexTabProps) {
  const [query, setQuery] = useState('')
  const typed = query.trim()

  const matches = useMemo(() => {
    if (!typed) return []
    const needle = typed.toLowerCase()
    return paths.filter((path) => path.toLowerCase().includes(needle)).sort((a, b) => a.localeCompare(b))
  }, [paths, typed])

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col" data-testid="files-index-tab">
      <div className="panel-search shrink-0">
        <Icon name="search" size={14} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') setQuery('') }}
          placeholder="Search files by path"
          aria-label="Search files"
          className="control-field"
        />
        {query && (
          <Button className="panel-search-clear" variant="ghost" size="icon-xs" onClick={() => setQuery('')} aria-label="Clear file search">
            <Icon name="close" size={13} />
          </Button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5" data-testid="files-index-results">
        {isLoading ? (
          <div className="flex flex-col gap-2 p-2" aria-label="Loading files">
            {[72, 84, 61, 78].map((width) => <div key={width} className="skeleton h-7" style={{ width: `${width}%` }} />)}
          </div>
        ) : typed ? (
          matches.length === 0 ? (
            <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>No matching files.</p>
          ) : (
            matches.map((path) => (
              <button
                key={path}
                type="button"
                data-testid={`files-search-result-${path}`}
                onClick={() => onSelect(path)}
                data-active={path === currentPath ? 'true' : 'false'}
                className="row-item"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  width: '100%',
                  padding: '6px 10px',
                  border: 'none',
                  color: path === currentPath ? 'var(--text)' : 'var(--text-2)',
                  fontSize: 12,
                  textAlign: 'left',
                  cursor: 'pointer',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <span className="truncate">{path}</span>
              </button>
            ))
          )
        ) : (
          <FileTree paths={paths} currentPath={currentPath} onSelect={onSelect} />
        )}
      </div>
    </div>
  )
}
