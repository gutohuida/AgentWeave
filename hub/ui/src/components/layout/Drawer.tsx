import * as Dialog from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { Icon } from '@/components/common/Icon'

/**
 * A pane shown as an overlay when there is not enough width to show it as a column.
 *
 * Radix Dialog gives the focus trap, Escape handling, and focus restoration this needs without
 * adding a dependency. Lifted out of `components/spec/SpecWorkspace.tsx` unchanged when that
 * three-column layout was replaced — the behaviour it carries is the same behaviour the document
 * panel needs below its fit threshold.
 */
export function Drawer({
  open,
  onOpenChange,
  title,
  side,
  width,
  triggerRef,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  side: 'left' | 'right'
  width: number
  /** Focus returns here on close, however the drawer was dismissed. */
  triggerRef: React.RefObject<HTMLButtonElement | null>
  children: ReactNode
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        {/* `z-50`, matching every other modal in the app — see `SpecDocumentPicker` for what
            happens without it. */}
        <Dialog.Overlay style={{ position: 'fixed', inset: 0, zIndex: 50, background: 'var(--scrim)' }} />
        <Dialog.Content
          aria-label={title}
          data-testid="workspace-drawer"
          // Restore focus to the control that opened the drawer rather than relying on which
          // element happened to be focused at mount time.
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            triggerRef.current?.focus()
          }}
          style={{
            position: 'fixed',
            zIndex: 50,
            top: 0,
            bottom: 0,
            [side]: 0,
            width: `min(${width}px, 92vw)`,
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface)',
            [side === 'left' ? 'borderRight' : 'borderLeft']: '1px solid var(--border)',
          }}
        >
          <div
            className="flex items-center justify-between px-3 py-2 shrink-0"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <Dialog.Title style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
              {title}
            </Dialog.Title>
            <Dialog.Close
              aria-label={`Close ${title}`}
              style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer' }}
            >
              <Icon name="close" size={16} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{title} panel.</Dialog.Description>
          <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
