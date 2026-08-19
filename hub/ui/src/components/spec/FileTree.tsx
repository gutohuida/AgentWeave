import { useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { buildFilePathTree } from './specNavigation'

const COLLAPSED_KEY = 'aw.files.treeCollapsed'

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

interface FileTreeProps {
  paths: readonly string[]
  currentPath?: string | null
  onSelect: (path: string) => void
}

/**
 * The workspace as its folder hierarchy — `SpecTree`'s counterpart for the files tab (task 5.1,
 * `2026-08-18-one-shell-three-panels`). Folders collapse and the collapsed set persists, under
 * its own storage key so folding a directory in the files tab never disturbs the specs tree's own
 * folded state.
 */
export function FileTree({ paths, currentPath = null, onSelect }: FileTreeProps) {
  const rows = useMemo(() => buildFilePathTree(paths), [paths])
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed)

  const toggle = (path: string) => {
    setCollapsed((state) => {
      const next = { ...state, [path]: !state[path] }
      try {
        localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next))
      } catch {
        // Persistence is optional.
      }
      return next
    })
  }

  const collapsedDirs = useMemo(
    () => Object.entries(collapsed).filter(([, isCollapsed]) => isCollapsed).map(([path]) => path),
    [collapsed],
  )
  const hidden = (path: string) =>
    collapsedDirs.some((dir) => path.startsWith(`${dir}/`) && path !== dir)

  const visible = rows.filter((row) => !hidden(row.path))

  if (rows.length === 0) {
    return (
      <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
        No files in this workspace yet.
      </p>
    )
  }

  return (
    <>
      {visible.map((row) =>
        row.kind === 'directory' ? (
          <button
            key={`dir:${row.path}`}
            type="button"
            data-testid={`file-tree-directory-${row.path}`}
            aria-expanded={!collapsed[row.path]}
            onClick={() => toggle(row.path)}
            title={row.path}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              padding: '7px 10px 3px',
              paddingLeft: 10 + row.depth * 14,
              border: 'none',
              background: 'none',
              fontSize: 11,
              fontWeight: 600,
              color: 'var(--text-3)',
              textAlign: 'left',
              cursor: 'pointer',
            }}
          >
            <span
              style={{
                display: 'inline-flex',
                transform: collapsed[row.path] ? undefined : 'rotate(90deg)',
                transition: 'transform var(--dur-fast) var(--ease)',
              }}
            >
              <Icon name="chevron_right" size={12} />
            </span>
            <Icon name="folder_open" size={12} />
            {row.label}
          </button>
        ) : (
          <button
            key={`file:${row.path}`}
            type="button"
            data-testid={`file-tree-file-${row.path}`}
            aria-current={row.path === currentPath ? 'true' : undefined}
            data-active={row.path === currentPath ? 'true' : 'false'}
            onClick={() => onSelect(row.path)}
            title={row.path}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '6px 10px',
              paddingLeft: 10 + row.depth * 14 + 18,
              border: 'none',
              background: row.path === currentPath ? 'var(--surface-2)' : 'none',
              color: row.path === currentPath ? 'var(--text)' : 'var(--text-2)',
              fontSize: 12,
              textAlign: 'left',
              cursor: 'pointer',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <Icon name="description" size={12} />
            <span className="truncate">{row.label}</span>
          </button>
        ),
      )}
    </>
  )
}
