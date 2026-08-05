import { useEffect, useRef, useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useDirectoryListing } from '@/api/fsBrowse'

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
 */
export function DirectoryPicker({ startPath, onChoose, onClose }: DirectoryPickerProps) {
  const [currentPath, setCurrentPath] = useState(startPath)
  const { data: listing, isLoading } = useDirectoryListing(currentPath)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', closeOnOutsidePointer)
    return () => document.removeEventListener('mousedown', closeOnOutsidePointer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Browse for a directory"
      className="absolute left-0 right-0 top-full mt-1 max-h-72 overflow-y-auto rounded border z-50"
      style={{
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
      }}
    >
      <div
        className="sticky top-0 flex items-center gap-1.5 px-2 py-1.5 text-xs"
        style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)', color: 'var(--text-3)' }}
      >
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="Up to parent directory"
          disabled={!listing?.parent}
          onClick={() => listing?.parent && setCurrentPath(listing.parent)}
        >
          <Icon name="arrow_upward" size={14} />
        </Button>
        <span className="min-w-0 flex-1 truncate" title={listing?.path ?? currentPath}>
          {listing?.path ?? currentPath}
        </span>
        <Button
          variant="primary"
          size="xs"
          onClick={() => onChoose(listing?.path ?? currentPath)}
          disabled={!listing?.path}
        >
          Choose this directory
        </Button>
      </div>

      {isLoading ? (
        <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-3)' }}>Loading…</p>
      ) : listing?.reason ? (
        <p role="status" className="px-3 py-3 text-xs" style={{ color: 'var(--amber)' }}>
          Can't read this directory: {listing.reason}
        </p>
      ) : listing && listing.entries.length === 0 ? (
        <p className="px-3 py-3 text-xs" style={{ color: 'var(--text-3)' }}>No subdirectories</p>
      ) : (
        listing?.entries.map((entry) => (
          <button
            key={entry.path}
            type="button"
            className="row-item w-full text-left"
            style={{ color: 'var(--text)' }}
            onClick={() => setCurrentPath(entry.path)}
            onDoubleClick={() => onChoose(entry.path)}
          >
            <Icon name="folder" size={14} style={{ color: 'var(--text-3)' }} />
            <span className="min-w-0 flex-1 truncate">{entry.name}</span>
          </button>
        ))
      )}
    </div>
  )
}
