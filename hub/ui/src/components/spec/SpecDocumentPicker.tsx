import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { searchDocuments, type SpecInventory, type SpecNode } from './specNavigation'
import { SpecTree } from './SpecTree'

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
  /**
   * Start an exploration with this title. Optional: the specification page's own
   * picker is for finding documents, and only the conversation surface is a place
   * where "there isn't one yet" is the answer.
   */
  onCreate?: (title: string) => void
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
  onCreate,
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
  const browsing = query.trim().length === 0

  const choose = (node: SpecNode) => {
    onSelect(node)
    onOpenChange(false)
  }

  /* Explore is the one phase that would otherwise precede its own document, which is why
   * starting one creates the document rather than setting a mode: without it, "propose" and
   * "approve" have no subject. It lives here because this is where an operator arrives having
   * discovered there is no document to open. */
  const typed = query.trim()
  const startExploration = onCreate
    ? () => {
        onCreate(typed)
        onOpenChange(false)
      }
    : null

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
            {startExploration && (browsing || empty) && (
              <button
                type="button"
                style={{ ...rowStyle, color: 'var(--text)' }}
                data-testid="spec-picker-start-exploration"
                onClick={startExploration}
                disabled={!browsing && !typed}
              >
                <Icon name="add" size={13} />
                <span className="truncate">
                  {typed ? `Start an exploration: ${typed}` : 'Start an exploration…'}
                </span>
              </button>
            )}
            {browsing ? (
              <SpecTree inventory={inventory} currentPath={currentPath} onSelect={choose} />
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
                  <button
                    key={node.path}
                    type="button"
                    style={{ ...rowStyle, opacity: 0.65 }}
                    onClick={() => choose(node)}
                  >
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
