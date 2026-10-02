import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DeleteCharterDialog } from '@/components/charters/DeleteCharterDialog'
import { ClearInstructionsDialog } from '@/components/instructions/ClearInstructionsDialog'
import { ArchiveConfirmDialog } from '@/components/spec/ArchiveConfirmDialog'

/** Fires the keydown the browser sends to a focused button on Enter, then the click it
 *  dispatches as a result — jsdom does not translate the first into the second itself. */
function pressEnterOn(element: Element) {
  fireEvent.keyDown(element, { key: 'Enter' })
  fireEvent.click(element)
}

describe('1.5 confirm-only dialogs — initial focus is Cancel', () => {
  it('DeleteCharterDialog: opens with focus on Cancel; Enter there calls onCancel, not onConfirm', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(<DeleteCharterDialog name="Widget" content="a\nb" onCancel={onCancel} onConfirm={onConfirm} />)

    const cancelButton = screen.getByText('Cancel')
    expect(document.activeElement).toBe(cancelButton)

    pressEnterOn(document.activeElement!)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('ClearInstructionsDialog: opens with focus on Cancel; Enter there calls onCancel, not onConfirm', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(
      <ClearInstructionsDialog
        projectName="Website"
        storedContent="a\nb\nc"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    )

    const cancelButton = screen.getByText('Cancel')
    expect(document.activeElement).toBe(cancelButton)

    pressEnterOn(document.activeElement!)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('ArchiveConfirmDialog: opens with focus on Cancel; Enter there calls onCancel, not onConfirm', () => {
    const onCancel = vi.fn()
    const onConfirm = vi.fn()
    render(
      <ArchiveConfirmDialog title="Ivory Hydra" isPending={false} onCancel={onCancel} onConfirm={onConfirm} />,
    )

    const cancelButton = screen.getByText('Cancel')
    expect(document.activeElement).toBe(cancelButton)

    pressEnterOn(document.activeElement!)
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
