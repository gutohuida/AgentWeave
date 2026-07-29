import { Icon } from '@/components/common/Icon'
import type { LibraryTreeNode, SpecInventory, SpecNode } from './specNavigation'
import type { LibraryMode } from './specPreferences'
import type { TocAnchor } from './specBridge'

interface SpecNavigatorProps {
  inventory: SpecInventory
  selectedPath: string | null
  mode: LibraryMode
  onModeChange: (mode: LibraryMode) => void
  onSelect: (path: string) => void
  onOpenSearch: () => void
  outline: TocAnchor[]
  activeSection: string | null
  onOutlineSelect: (id: string) => void
}

const rowBase: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  width: '100%',
  padding: '4px 8px',
  border: 'none',
  background: 'none',
  color: 'var(--text-2)',
  fontSize: 12,
  textAlign: 'left',
  cursor: 'pointer',
  borderRadius: 'var(--radius-sm)',
}

function DocumentRow({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: SpecNode
  depth: number
  selected: boolean
  onSelect: (path: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(node.path)}
      title={node.path}
      aria-current={selected ? 'true' : undefined}
      style={{
        ...rowBase,
        paddingLeft: 8 + depth * 12,
        background: selected ? 'var(--surface-3)' : 'none',
        color: selected ? 'var(--text)' : 'var(--text-2)',
      }}
    >
      <span className="truncate">{node.title}</span>
    </button>
  )
}

function LibraryBranch({
  nodes,
  depth,
  selectedPath,
  onSelect,
}: {
  nodes: LibraryTreeNode[]
  depth: number
  selectedPath: string | null
  onSelect: (path: string) => void
}) {
  return (
    <>
      {nodes.map((entry) => (
        <div key={entry.node.path}>
          <DocumentRow
            node={entry.node}
            depth={depth}
            selected={entry.node.path === selectedPath}
            onSelect={onSelect}
          />
          {entry.children.length > 0 && (
            <LibraryBranch
              nodes={entry.children}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          )}
        </div>
      ))}
    </>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        padding: '8px 8px 4px',
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '.06em',
        textTransform: 'uppercase',
        color: 'var(--text-3)',
      }}
    >
      {children}
    </div>
  )
}

export function SpecNavigator({
  inventory,
  selectedPath,
  mode,
  onModeChange,
  onSelect,
  onOpenSearch,
  outline,
  activeSection,
  onOutlineSelect,
}: SpecNavigatorProps) {
  const showHistory = mode === 'history'

  return (
    <div className="flex flex-col h-full min-h-0" data-testid="spec-navigator">
      <div className="flex items-center gap-1 px-2 py-2 shrink-0">
        <button
          type="button"
          onClick={onOpenSearch}
          className="flex-1 truncate"
          style={{
            ...rowBase,
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            color: 'var(--text-3)',
          }}
        >
          <Icon name="search" size={14} />
          <span>Search documents</span>
          <span style={{ marginLeft: 'auto', fontSize: 10 }}>Ctrl K</span>
        </button>
      </div>

      <div
        className="flex items-center gap-1 px-2 pb-2 shrink-0"
        role="tablist"
        aria-label="Document scope"
      >
        {(['library', 'history'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={mode === value}
            onClick={() => onModeChange(value)}
            style={{
              ...rowBase,
              width: 'auto',
              flex: 1,
              justifyContent: 'center',
              background: mode === value ? 'var(--surface-3)' : 'none',
              color: mode === value ? 'var(--text)' : 'var(--text-3)',
            }}
          >
            {value === 'library' ? 'Library' : 'History'}
          </button>
        ))}
      </div>

      {/* Documents — scrolls independently of the page outline below. */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2" data-testid="spec-document-list">
        {showHistory ? (
          inventory.history.length === 0 ? (
            <p style={{ padding: 8, fontSize: 11, color: 'var(--text-3)' }}>No archived changes.</p>
          ) : (
            inventory.history.map((group) => (
              <div key={group.label}>
                <SectionLabel>{group.label}</SectionLabel>
                {group.entries.map((node) => (
                  <DocumentRow
                    key={node.path}
                    node={node}
                    depth={1}
                    selected={node.path === selectedPath}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            ))
          )
        ) : (
          <>
            {inventory.library.length === 0 && inventory.needsAttention.length === 0 && (
              <p style={{ padding: 8, fontSize: 11, color: 'var(--text-3)' }}>No documents.</p>
            )}
            <LibraryBranch
              nodes={inventory.library}
              depth={0}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
            {inventory.needsAttention.length > 0 && (
              <div data-testid="spec-needs-attention">
                <SectionLabel>Needs attention</SectionLabel>
                {inventory.needsAttention.map((node) =>
                  node.missing ? (
                    // Missing documents stay visible so drift is never hidden,
                    // but they cannot be opened.
                    <span
                      key={node.path}
                      title={`${node.path} — declared in the manifest, file not found`}
                      style={{ ...rowBase, cursor: 'not-allowed', opacity: 0.55 }}
                    >
                      <span className="truncate">{node.title}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 10 }}>missing</span>
                    </span>
                  ) : (
                    <DocumentRow
                      key={node.path}
                      node={node}
                      depth={1}
                      selected={node.path === selectedPath}
                      onSelect={onSelect}
                    />
                  )
                )}
              </div>
            )}
          </>
        )}
      </div>

      {outline.length > 0 && (
        <div
          className="shrink-0 overflow-y-auto px-2"
          style={{ maxHeight: '40%', borderTop: '1px solid var(--border)' }}
          data-testid="spec-outline"
        >
          <SectionLabel>On this page</SectionLabel>
          <nav aria-label="Page outline">
            {outline.map((anchor) => (
              <button
                key={anchor.id}
                type="button"
                onClick={() => onOutlineSelect(anchor.id)}
                aria-current={activeSection === anchor.id ? 'true' : undefined}
                style={{
                  ...rowBase,
                  fontSize: 11,
                  color: activeSection === anchor.id ? 'var(--text)' : 'var(--text-3)',
                  background: activeSection === anchor.id ? 'var(--surface-3)' : 'none',
                }}
              >
                <span className="truncate">{anchor.label}</span>
              </button>
            ))}
          </nav>
        </div>
      )}
    </div>
  )
}
