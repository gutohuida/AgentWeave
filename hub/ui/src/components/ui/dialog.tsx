import * as React from 'react'
import * as RadixDialog from '@radix-ui/react-dialog'
import { Icon } from '@/components/common/Icon'

/** The one dialog. Backdrop fades in over 200ms with a 4px blur; the panel scales from .98 and
 *  fades on the out-curve, and leaves faster (150ms) than it came. Focus is trapped and returned
 *  to the trigger (Radix). Anchored a fixed distance from the top, not centred, so a dialog whose
 *  content grows (an error appears, a list loads) grows downward instead of jumping. */

export const Dialog = RadixDialog.Root
export const DialogTrigger = RadixDialog.Trigger
export const DialogClose = RadixDialog.Close

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
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className="aw-dialog-overlay" />
      <RadixDialog.Content className="aw-dialog" style={{ width: `min(${width}px, calc(100vw - 32px))` }}>
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
