import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { buildPathTree, searchDocuments, type SpecInventory, type SpecNode } from './specNavigation'

interface SpecDocumentPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  inventory: SpecInventory
  onSelect: (node: SpecNode) => void
  /**
   * Where focus goes on close. Supplied by the page because the picker can be
   * opened from the search button or from the Ctrl/Cmd+K shortcut, so it has
   * no single trigger of its own.
   */
  restoreFocusTo?: () => HTMLElement | null
  /** The document already open, marked in the tree so the operator can see where they are. */
  currentPath?: string | null
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  padding: '6px 10px',
  border: 'none',
  background: 'none',
  color: 'var(--text-2)',
  fontSize: 12,
  textAlign: 'left',
  cursor: 'pointer',
  borderRadius: 'var(--radius-sm)',
}

/** What sits on the right of a tree row.
 *
 *  The filename is there to disambiguate a column of change directories that all contain
 *  `spec.html` — so it is worth nothing when the document has no manifest title and its label
 *  *is* the filename, which printed `a1-probe.html` twice on one row. Drift and archive dates
 *  outrank it: they say something the label cannot. */
function trailingLabel(label: string, path: string, node?: SpecNode): string {
  if (node?.missing) return 'missing'
  if (node?.archived) return node.archiveDate ?? 'archived'
  const filename = path.slice(path.lastIndexOf('/') + 1)
  return filename === label ? '' : filename
}

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        padding: '8px 10px 4px',
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

/**
 * Ctrl/Cmd+K document search. Radix Dialog supplies the focus trap, Escape
 * handling, and focus restoration required by FR-9 without a new dependency.
 */
export function SpecDocumentPicker({
  open,
  onOpenChange,
  inventory,
  onSelect,
  restoreFocusTo,
  currentPath = null,
}: SpecDocumentPickerProps) {
  const [query, setQuery] = useState('')

  // Each opening starts a fresh search rather than resuming a stale one.
  useEffect(() => {
    if (open) setQuery('')
  }, [open])

  const results = useMemo(() => searchDocuments(inventory, query), [inventory, query])
  const empty =
    results.current.length === 0 && results.archived.length === 0 && results.missing.length === 0

  /* With nothing typed, the picker shows the specification as it is actually organised rather
   * than an empty box waiting to be told what to look for. Typing replaces it with matches: a
   * tree is for finding your way around something you cannot yet name, a ranked flat list is for
   * when you can. */
  const tree = useMemo(() => buildPathTree(inventory.nodes), [inventory])
  const browsing = query.trim().length === 0

  const choose = (node: SpecNode) => {
    onSelect(node)
    onOpenChange(false)
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        {/* `z-50`, matching every other modal in the app. Without it the overlay and the dialog
            sit at `z-index: auto`, and `.conversation-header-surface`'s `z-index: 3` — which
            exists so the blurred header sits above the scrolling output — paints the conversation
            header straight over the top of them. A portal is later in the document but that only
            decides order between elements at the same level. */}
        <Dialog.Overlay style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'var(--scrim)' }} />
        <Dialog.Content
          aria-label="Search documents"
          onCloseAutoFocus={(event) => {
            const target = restoreFocusTo?.()
            if (!target) return
            event.preventDefault()
            target.focus()
          }}
          style={{
            position: 'fixed',
            zIndex: 50,
            top: '12vh',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'min(560px, 92vw)',
            maxHeight: '70vh',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            overflow: 'hidden',
          }}
        >
          <Dialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
            Search documents
          </Dialog.Title>
          <Dialog.Description className="sr-only">
            Search current and archived specification documents by title, path, or change name.
          </Dialog.Description>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title, path, or change name — or browse below"
            aria-label="Search documents"
            style={{
              padding: '12px 14px',
              border: 'none',
              borderBottom: '1px solid var(--border)',
              background: 'transparent',
              color: 'var(--text)',
              fontSize: 13,
              outline: 'none',
            }}
          />
          <div className="overflow-y-auto p-1.5" data-testid="spec-picker-results">
            {browsing ? (
              tree.length === 0 ? (
                <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>
                  No specification documents yet.
                </p>
              ) : (
                tree.map((row) =>
                  row.kind === 'directory' ? (
                    <div
                      key={`dir:${row.path}`}
                      data-testid={`spec-picker-directory-${row.path}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        padding: '7px 10px 3px',
                        paddingLeft: 10 + row.depth * 14,
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
                      data-testid={`spec-picker-document-${row.path}`}
                      // Missing documents stay visible so drift is never hidden, and unselectable
                      // because there is nothing to open.
                      disabled={row.node?.missing}
                      aria-current={row.path === currentPath ? 'true' : undefined}
                      data-active={row.path === currentPath ? 'true' : 'false'}
                      onClick={() => row.node && choose(row.node)}
                      style={{
                        ...rowStyle,
                        paddingLeft: 10 + row.depth * 14,
                        ...(row.node?.missing ? { cursor: 'not-allowed', opacity: 0.55 } : null),
                        ...(row.path === currentPath
                          ? { background: 'var(--surface-2)', color: 'var(--text)' }
                          : null),
                      }}
                    >
                      <Icon name="article" size={12} />
                      <span className="truncate">{row.label}</span>
                      <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-3)' }}>
                        {trailingLabel(row.label, row.path, row.node)}
                      </span>
                    </button>
                  ),
                )
              )
            ) : (
              <>
            {empty && (
              <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>No matching documents.</p>
            )}

            {results.current.map((node) => (
              <button key={node.path} type="button" style={rowStyle} onClick={() => choose(node)}>
                <span className="truncate">{node.title}</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-3)' }}>
                  {node.path}
                </span>
              </button>
            ))}

            {results.archived.length > 0 && (
              <>
                <GroupLabel>Archived</GroupLabel>
                {results.archived.map((node) => (
                  <button key={node.path} type="button" style={rowStyle} onClick={() => choose(node)}>
                    <span className="truncate">{node.title}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-3)' }}>
                      {node.archiveDate ?? node.path}
                    </span>
                  </button>
                ))}
              </>
            )}

            {results.missing.length > 0 && (
              <>
                <GroupLabel>Missing</GroupLabel>
                {results.missing.map((node) => (
                  // Discoverable so drift is visible, but never selectable.
                  <button
                    key={node.path}
                    type="button"
                    disabled
                    style={{ ...rowStyle, cursor: 'not-allowed', opacity: 0.55 }}
                  >
                    <span className="truncate">{node.title}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 10 }}>missing</span>
                  </button>
                ))}
              </>
            )}
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
