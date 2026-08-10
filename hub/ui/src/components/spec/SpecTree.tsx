import { useMemo } from 'react'
import { Icon } from '@/components/common/Icon'
import { buildPathTree, type SpecInventory, type SpecNode } from './specNavigation'

interface SpecTreeProps {
  inventory: SpecInventory
  /** Marked as current, so the tree says where the operator is. */
  currentPath?: string | null
  onSelect: (node: SpecNode) => void
  /** Row height and type scale. `dialog` is the Ctrl+K picker; `rail` is the Spec screen's own
   *  navigation column, which sits next to the Hub rail and matches its density. */
  density?: 'dialog' | 'rail'
}

/**
 * The specification as its folder hierarchy.
 *
 * One implementation, two homes: the Ctrl+K picker shows it when nothing has been typed, and the
 * Spec screen shows it as its navigation column. They are the same list with the same rules —
 * shared directories named once, archives and missing documents included, missing ones
 * unselectable — so they are the same component rather than two that have to be kept in step.
 */
export function SpecTree({ inventory, currentPath = null, onSelect, density = 'dialog' }: SpecTreeProps) {
  const rows = useMemo(() => buildPathTree(inventory.nodes), [inventory])
  const indent = density === 'rail' ? 12 : 14
  const fontSize = density === 'rail' ? 12 : 12

  if (rows.length === 0) {
    return (
      <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
        No specification documents yet.
      </p>
    )
  }

  return (
    <>
      {rows.map((row) =>
        row.kind === 'directory' ? (
          <div
            key={`dir:${row.path}`}
            data-testid={`spec-tree-directory-${row.path}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '7px 10px 3px',
              paddingLeft: 10 + row.depth * indent,
              fontSize: 11,
              fontWeight: 600,
              color: 'var(--text-3)',
            }}
          >
            <Icon name="folder_open" size={12} />
            {row.label}
          </div>
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
              paddingLeft: 10 + row.depth * indent,
              border: 'none',
              background: row.path === currentPath ? 'var(--surface-2)' : 'none',
              color: row.path === currentPath ? 'var(--text)' : 'var(--text-2)',
              fontSize,
              textAlign: 'left',
              cursor: row.node?.missing ? 'not-allowed' : 'pointer',
              opacity: row.node?.missing ? 0.55 : 1,
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <Icon name="article" size={12} />
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
