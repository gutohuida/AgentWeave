import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DeleteCharterDialog } from '@/components/charters/DeleteCharterDialog'
import { ClearInstructionsDialog } from '@/components/instructions/ClearInstructionsDialog'
import { ArchiveConfirmDialog } from '@/components/spec/ArchiveConfirmDialog'

function ArchiveHarness({ isPending }: { isPending: boolean }) {
  return <ArchiveConfirmDialog title="Ivory Hydra" isPending={isPending} onCancel={() => {}} onConfirm={() => {}} />
}

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

describe('1.13 ArchiveConfirmDialog — focus moves to the panel when isPending becomes true', () => {
  it('Archive holds focus, then isPending turns true: focus moves off the now-disabled button, to the panel', () => {
    const { container, rerender } = render(<ArchiveHarness isPending={false} />)

    const archiveButton = screen.getByText('Archive')
    archiveButton.focus()
    expect(document.activeElement).toBe(archiveButton)

    rerender(<ArchiveHarness isPending={true} />)

    const panel = container.querySelector('[tabindex="-1"]')
    expect(document.activeElement).not.toBe(archiveButton)
    expect(document.activeElement).toBe(panel)
  })
})
