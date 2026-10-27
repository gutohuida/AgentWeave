import * as Dialog from '@radix-ui/react-dialog'
import { SpecPickerContainer } from './page/SpecPanelContainer'

interface SpecDocumentPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Open the chosen document, for reading. */
  onSelect: (path: string) => void
  /** Where focus goes on close; the picker opens from a button or a shortcut, so it has no trigger of its own. */
  restoreFocusTo?: () => HTMLElement | null
  /** The document already open, marked in the list. */
  currentPath?: string | null
  /** The conversation's attached document, shown first among the shortcuts. */
  attachedPath?: string | null
  /** Documents opened lately, most recent first. */
  recent?: string[]
  /** Start a new change. Optional: the specification page has no conversation to start it in. */
  onNew?: () => void
}

/**
 * The Ctrl/Cmd+Shift+K document picker: the same picker as the panel's Specs tab and switcher
 * (`SpecOpenPicker`), in a dialog. Radix supplies the focus trap, Escape and focus restoration; the
 * content unmounts when closed, which resets the search field.
 */
export function SpecDocumentPicker({ open, onOpenChange, onSelect, restoreFocusTo, currentPath = null, attachedPath, recent, onNew }: SpecDocumentPickerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
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
            top: '10vh',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'min(560px, 92vw)',
            maxHeight: '75vh',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            overflow: 'auto',
          }}
        >
          <Dialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Search documents</Dialog.Title>
          <Dialog.Description className="sr-only">Search the project's specification documents by title or path.</Dialog.Description>
          <SpecPickerContainer
            autoFocus
            openPath={currentPath}
            attachedPath={attachedPath}
            recent={recent}
            onNew={() => {
              onNew?.()
              onOpenChange(false)
            }}
            onOpen={(path) => {
              onSelect(path)
              onOpenChange(false)
            }}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
