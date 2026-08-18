import * as Dialog from '@radix-ui/react-dialog'
import { SpecDocumentBrowser } from './SpecDocumentBrowser'
import type { SpecInventory, SpecNode } from './specNavigation'

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

/**
 * Ctrl/Cmd+K document search. Radix Dialog supplies the focus trap, Escape
 * handling, and focus restoration required by FR-9 without a new dependency.
 *
 * The search-and-browse content is `SpecDocumentBrowser` — shared with the panel shell's `specs`
 * index tab (task 3.1, `2026-08-18-one-shell-three-panels`) — so this component owns only the
 * dialog chrome. Radix does not render `Dialog.Content` while `open` is false, so the browser
 * unmounts and remounts across an open/close cycle, which is what resets its search box without
 * this component having to do it itself.
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
  const choose = (node: SpecNode) => {
    onSelect(node)
    onOpenChange(false)
  }

  const startExploration = onCreate
    ? (title: string) => {
        onCreate(title)
        onOpenChange(false)
      }
    : undefined

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
          <SpecDocumentBrowser
            inventory={inventory}
            currentPath={currentPath}
            onSelect={choose}
            onCreate={startExploration}
            autoFocus
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
