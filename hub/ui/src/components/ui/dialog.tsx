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

interface DialogContentProps {
  title: string
  description?: React.ReactNode
  width?: number
  footer?: React.ReactNode
  children?: React.ReactNode
}

export function DialogContent(props: DialogContentProps) {
  return (
    <RadixDialog.Portal>
      <DialogPanel {...props} />
    </RadixDialog.Portal>
  )
}

/** Mounted only while the dialog is open (inside the Portal), which is what lets it read, once,
 *  what had focus when it opened.
 *
 *  Radix returns focus to the dialog's Trigger on close. A dialog opened from a button that is not
 *  wrapped in one (every controlled dialog: the Vault's Add and Vault storage, the Jobs archive
 *  confirm) has none, and focus fell to <body> (F1029). The element focused at open is the opener
 *  whether a button was pressed or a shortcut used, so no caller has to say where focus goes back
 *  to. Opened with nothing focused (a file dropped on the Vault), there is nothing to return to. */
function DialogPanel({ title, description, width = 520, footer, children }: DialogContentProps) {
  const [opener] = React.useState<HTMLElement | null>(() =>
    typeof document !== 'undefined' && document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null,
  )
  return (
    <>
      <RadixDialog.Overlay className="aw-dialog-overlay" />
      <RadixDialog.Content
        className="aw-dialog"
        style={{ width: `min(${width}px, calc(100vw - 32px))` }}
        onCloseAutoFocus={(event) => {
          if (opener?.isConnected) {
            event.preventDefault()
            opener.focus()
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
    </>
  )
}
