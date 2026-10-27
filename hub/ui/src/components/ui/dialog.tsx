import * as React from 'react'
import * as RadixDialog from '@radix-ui/react-dialog'
import { Icon } from '@/components/common/Icon'

/** The one dialog. Backdrop fades in over 200ms with a 4px blur; the panel scales from .98 and
 *  fades on the out-curve, and leaves faster (150ms) than it came. Focus is trapped and returned
 *  to whatever had it when the dialog opened. Anchored a fixed distance from the top, not centred,
 *  so a dialog whose content grows (an error appears, a list loads) grows downward instead of
 *  jumping. */

export const Dialog = RadixDialog.Root
export const DialogTrigger = RadixDialog.Trigger
export const DialogClose = RadixDialog.Close

/** The control to give focus back to, given what has it as the dialog opens.
 *
 *  A dialog opened from a menu item is opened by an element that is unmounted as the menu closes
 *  (the Jobs archive confirm), so it can never be returned to; the menu's own trigger can. Radix
 *  labels a menu by its trigger (`aria-labelledby`) and the trigger controls it (`aria-controls`). */
function openerOf(active: Element | null): HTMLElement | null {
  if (!(active instanceof HTMLElement) || active === document.body) return null
  const menu = active.closest('[role="menu"]')
  if (!menu) return active
  const labelledBy = menu.getAttribute('aria-labelledby')
  const trigger =
    (labelledBy ? document.getElementById(labelledBy) : null) ??
    (menu.id ? document.querySelector(`[aria-controls="${CSS.escape(menu.id)}"]`) : null)
  return trigger instanceof HTMLElement ? trigger : null
}

export function DialogContent({
  title,
  description,
  width = 520,
  footer,
  children,
}: {
  title: string
  description?: React.ReactNode
  width?: number
  footer?: React.ReactNode
  children?: React.ReactNode
}) {
  // Radix returns focus to the dialog's Trigger on close. A dialog opened from a button that is not
  // wrapped in one (every controlled dialog: the Vault's Add and Vault storage, the Jobs archive
  // confirm) has none, and focus fell to <body> (F1029). Whatever had focus as the dialog opens is
  // the opener, whether a button was pressed or a shortcut used, so no caller says where focus goes
  // back to. It is read in `onOpenAutoFocus`, which runs before Radix moves focus into the dialog.
  // Overlay and Content stay direct children of the Portal: Radix hands each a ref for its exit
  // animation, which a wrapper component cannot take.
  const opener = React.useRef<HTMLElement | null>(null)
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="aw-dialog-overlay" />
      <RadixDialog.Content
        className="aw-dialog"
        style={{ width: `min(${width}px, calc(100vw - 32px))` }}
        onOpenAutoFocus={() => {
          opener.current = openerOf(document.activeElement)
        }}
        onCloseAutoFocus={(event) => {
          const target = opener.current
          opener.current = null
          if (target?.isConnected) {
            event.preventDefault()
            target.focus()
          }
        }}
      >
        <header className="aw-dialog-head">
          <div className="min-w-0">
            <RadixDialog.Title className="aw-dialog-title">{title}</RadixDialog.Title>
            {description ? <RadixDialog.Description className="aw-dialog-desc">{description}</RadixDialog.Description> : null}
          </div>
          <RadixDialog.Close data-slot="icon-button" className="aw-icon-button" aria-label="Close">
            <Icon name="close" size={14} />
          </RadixDialog.Close>
        </header>
        {children ? <div className="aw-dialog-body">{children}</div> : null}
        {footer ? <footer className="aw-dialog-foot">{footer}</footer> : null}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  )
}
