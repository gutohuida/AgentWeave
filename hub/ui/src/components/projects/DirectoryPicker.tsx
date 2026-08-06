import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useDirectoryListing, useFilesystemRoots } from '@/api/fsBrowse'
import { pathAncestors } from '@/lib/pathDisplay'

interface DirectoryPickerProps {
  /** The directory to open the picker on — the typed path if it looks absolute, else the
   * operator starts navigation from wherever they last were. */
  startPath: string
  onChoose: (path: string) => void
  onClose: () => void
}

/**
 * Browses Hub-visible directories to choose a project path — supplements the text input
 * rather than replacing it (2026-08-04-hub-model-control-and-provisioning design.md):
 * typing a known path is still available and unaffected by this component existing.
 *
 * Choosing the current directory has exactly one path: the visible "Choose this
 * directory" control. There is no double-click shortcut (composer/chrome refinement
 * §9.3, operator feedback: "requires a double-click... an undiscoverable distinction
 * with no affordance") — a single click always navigates, never chooses.
 */
export function DirectoryPicker({ startPath, onChoose, onClose }: DirectoryPickerProps) {
  const [currentPath, setCurrentPath] = useState(startPath)
  const [highlighted, setHighlighted] = useState(0)
  const { data: listing, isLoading } = useDirectoryListing(currentPath)
  const { data: rootsData } = useFilesystemRoots()
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setHighlighted(0)
  }, [listing?.path])

  const entries = listing?.entries ?? []
  const breadcrumb = pathAncestors(listing?.path ?? currentPath)
  const roots = rootsData?.roots ?? []

  function goToParent() {
    if (listing?.parent) setCurrentPath(listing.parent)
  }

  function chooseCurrent() {
    onChoose(listing?.path ?? currentPath)
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((h) => Math.min(h + 1, entries.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((h) => Math.max(h - 1, 0))
      return
    }
    if (event.key === 'Backspace') {
      event.preventDefault()
      goToParent()
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const target = entries[highlighted]
      if (target) setCurrentPath(target.path)
    }
  }

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Browse for a directory"
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      className="absolute left-0 right-0 top-full mt-1 max-h-80 overflow-y-auto rounded border z-50"
      style={{
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
      }}
    >
      {roots.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-1 px-2 py-1.5"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          {roots.map((root) => (
            <button
              key={root.path}
              type="button"
              className="row-item w-auto shrink-0 px-2"
              style={{ color: 'var(--text-2)' }}
              onClick={() => setCurrentPath(root.path)}
            >
              <Icon name="home" size={13} />
              {root.name}
            </button>
          ))}
        </div>
      )}

      <div
        className="flex flex-wrap items-center gap-x-1 gap-y-0.5 px-2 py-1.5 text-xs"
        style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-3)' }}
      >
        {breadcrumb.map((ancestor, index) => (
          <span key={ancestor.path} className="flex items-center gap-1">
            {index > 0 && <span aria-hidden="true">›</span>}
            <button
              type="button"
              className="rounded px-1 hover:underline"
              style={{ color: index === breadcrumb.length - 1 ? 'var(--text)' : 'var(--text-3)' }}
              onClick={() => setCurrentPath(ancestor.path)}
            >
              {ancestor.label}
            </button>
          </span>
        ))}
      </div>

      <div
        className="flex items-center justify-between gap-2 px-2 py-1.5"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Up to parent directory"
          disabled={!listing?.parent}
          onClick={goToParent}
        >
          <Icon name="arrow_upward" size={14} />
        </Button>
        <Button variant="primary" size="xs" onClick={chooseCurrent} disabled={!listing?.path}>
          Choose this directory
        </Button>
      </div>

      {isLoading ? (
        <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-3)' }}>Loading…</p>
      ) : listing?.reason ? (
        <p role="status" className="px-3 py-3 text-xs" style={{ color: 'var(--amber)' }}>
          Can't read this directory: {listing.reason}
        </p>
      ) : entries.length === 0 ? (
        <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-3)' }}>No subdirectories</p>
      ) : (
        <div role="listbox" aria-label="Directory entries">
          {entries.map((entry, index) => (
            <button
              key={entry.path}
              type="button"
              role="option"
              aria-selected={index === highlighted}
              data-highlighted={index === highlighted ? 'true' : 'false'}
              className="row-item w-full text-left"
              style={{ color: 'var(--text)', background: index === highlighted ? 'var(--row-hover)' : undefined }}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => setCurrentPath(entry.path)}
            >
              <Icon name="folder" size={14} style={{ color: 'var(--text-3)' }} />
              <span className="min-w-0 flex-1 truncate">{entry.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
