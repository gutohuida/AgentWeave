import { useMemo, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { searchDocuments, type SpecInventory, type SpecNode } from './specNavigation'
import { SpecTree } from './SpecTree'

interface SpecDocumentBrowserProps {
  inventory: SpecInventory
  /** The document already open, marked in the tree so the operator can see where they are. */
  currentPath?: string | null
  onSelect: (node: SpecNode) => void
  /**
   * Start an exploration with this title. Optional: not every home this browser is hosted in
   * has somewhere to send a newly-created document's conversation.
   */
  onCreate?: (title: string) => void
  autoFocus?: boolean
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
 * Search-and-browse over the project's specification documents: current, archived, and missing.
 *
 * One implementation, two homes — the Ctrl/Cmd+K dialog (`SpecDocumentPicker`) and the panel
 * shell's `specs` index tab (`SpecIndexTab`) — the same reason `SpecTree` already serves the
 * dialog and the rail: the content and its rules do not change with the chrome around it.
 */
export function SpecDocumentBrowser({
  inventory,
  currentPath = null,
  onSelect,
  onCreate,
  autoFocus = false,
}: SpecDocumentBrowserProps) {
  const [query, setQuery] = useState('')

  const results = useMemo(() => searchDocuments(inventory, query), [inventory, query])
  const empty =
    results.current.length === 0 && results.archived.length === 0 && results.missing.length === 0

  /* With nothing typed, the browser shows the specification as it is actually organised rather
   * than an empty box waiting to be told what to look for. Typing replaces it with matches: a
   * tree is for finding your way around something you cannot yet name, a ranked flat list is for
   * when you can. */
  const browsing = query.trim().length === 0

  /* Explore is the one phase that would otherwise precede its own document, which is why
   * starting one creates the document rather than setting a mode: without it, "propose" and
   * "approve" have no subject. It lives here because this is where an operator arrives having
   * discovered there is no document to open. */
  const typed = query.trim()
  const startExploration = onCreate ? () => onCreate(typed) : null

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col" data-testid="spec-document-browser">
      <input
        autoFocus={autoFocus}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search by title, path, or change name — or browse below"
        aria-label="Search documents"
        className="shrink-0"
        style={{
          padding: '12px 14px',
          border: 'none',
          background: 'transparent',
          color: 'var(--text)',
          fontSize: 13,
          outline: 'none',
        }}
      />
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5" data-testid="spec-picker-results">
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
          <SpecTree inventory={inventory} currentPath={currentPath} onSelect={onSelect} />
        ) : (
          <>
            {empty && (
              <p style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>No matching documents.</p>
            )}

            {results.current.map((node) => (
              <button key={node.path} type="button" style={rowStyle} onClick={() => onSelect(node)}>
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
                    onClick={() => onSelect(node)}
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
    </div>
  )
}
