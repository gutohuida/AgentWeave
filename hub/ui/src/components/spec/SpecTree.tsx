import { useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { buildPathTree, type SpecInventory, type SpecNode } from './specNavigation'

const COLLAPSED_KEY = 'aw.spec.treeCollapsed'

function loadCollapsed(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '{}') as Record<string, boolean>
  } catch {
    return {}
  }
}

interface SpecTreeProps {
  inventory: SpecInventory
  /** Marked as current, so the tree says where the operator is. */
  currentPath?: string | null
  onSelect: (node: SpecNode) => void
  /** Row height and type scale. `dialog` is the Ctrl+K picker; `rail` is the navigation rail,
   *  which matches the density of the project tree it stands in for. */
  density?: 'dialog' | 'rail'
}

/**
 * The specification as its folder hierarchy.
 *
 * One implementation, two homes: the Ctrl+K picker shows it when nothing has been typed, and the
 * rail shows it while the Spec screen is open. They are the same list with the same rules — shared
 * directories named once, archives and missing documents included, missing ones unselectable — so
 * they are the same component rather than two that have to be kept in step.
 *
 * Folders collapse, and the collapsed set is shared between both homes and persisted: a tree that
 * forgets what you folded away is a tree you fold away again every time.
 */
export function SpecTree({ inventory, currentPath = null, onSelect, density = 'dialog' }: SpecTreeProps) {
  const rows = useMemo(() => buildPathTree(inventory.nodes), [inventory])
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(loadCollapsed)
  const indent = density === 'rail' ? 12 : 14

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
  /** Hidden when any ancestor is folded. Tested by path prefix rather than by threading a parent
   *  through every row: the paths already encode the hierarchy, and a folded grandparent has to
   *  hide a nested directory as surely as it hides a document. */
  const hidden = (path: string) =>
    collapsedDirs.some((dir) => path.startsWith(`${dir}/`) && path !== dir)

  const visible = rows.filter((row) => !hidden(row.path))

  if (rows.length === 0) {
    return (
      <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
        No specification documents yet.
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
            data-testid={`spec-tree-directory-${row.path}`}
            aria-expanded={!collapsed[row.path]}
            onClick={() => toggle(row.path)}
            title={row.path}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              padding: '7px 10px 3px',
              paddingLeft: 10 + row.depth * indent,
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
            key={`doc:${row.path}`}
            type="button"
            data-testid={`spec-tree-document-${row.path}`}
            // Missing documents stay visible so drift is never hidden, and unselectable because
            // there is nothing to open.
            disabled={row.node?.missing}
            aria-current={row.path === currentPath ? 'true' : undefined}
            data-active={row.path === currentPath ? 'true' : 'false'}
            onClick={() => row.node && onSelect(row.node)}
            title={row.path}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              width: '100%',
              padding: '6px 10px',
              // Aligned with the folder label rather than the chevron, so a document reads as
              // being *in* the folder above it.
              paddingLeft: 10 + row.depth * indent + 18,
              border: 'none',
              background: row.path === currentPath ? 'var(--surface-2)' : 'none',
              color: row.path === currentPath ? 'var(--text)' : 'var(--text-2)',
              fontSize: 12,
              textAlign: 'left',
              cursor: row.node?.missing ? 'not-allowed' : 'pointer',
              // Archived is dimmed but still openable, unlike missing — one is drift, the other is
              // a document the operator can still choose to read, just not one that is current.
              opacity: row.node?.missing ? 0.55 : row.node?.archived ? 0.65 : 1,
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <Icon name={row.node?.archived ? 'archive' : 'article'} size={12} />
            <span className="truncate">{row.label}</span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-3)' }}>
              {trailingLabel(row.label, row.path, row.node)}
            </span>
          </button>
        ),
      )}
    </>
  )
}

/** What sits on the right of a row.
 *
 *  The filename disambiguates a column of change directories that all contain `spec.html` — so it
 *  is worth nothing when the document has no manifest title and its label *is* the filename,
 *  which printed `a1-probe.html` twice on one row. Drift and archive dates outrank it: they say
 *  something the label cannot. */
function trailingLabel(label: string, path: string, node?: SpecNode): string {
  if (node?.missing) return 'missing'
  if (node?.archived) return node.archiveDate ?? 'archived'
  const filename = path.slice(path.lastIndexOf('/') + 1)
  return filename === label ? '' : filename
}
