import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PaneResizer } from '@/components/layout/PaneResizer'

function setup(width = 220) {
  const onChange = vi.fn()
  render(
    <PaneResizer
      width={width}
      onChange={onChange}
      defaultWidth={220}
      min={180}
      max={420}
    />,
  )
  return { onChange, resizer: screen.getByTestId('pane-resizer') }
}

describe('PaneResizer', () => {
  it('exposes itself as a separator with its current and bounding values', () => {
    const { resizer } = setup(260)
    expect(resizer).toHaveAttribute('role', 'separator')
    expect(resizer).toHaveAttribute('aria-orientation', 'vertical')
    expect(resizer).toHaveAttribute('aria-valuenow', '260')
    expect(resizer).toHaveAttribute('aria-valuemin', '180')
    expect(resizer).toHaveAttribute('aria-valuemax', '420')
  })

  it('resizes by keyboard so it is operable without a pointer', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(220)

    resizer.focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith(228)

    await user.keyboard('{ArrowLeft}')
    expect(onChange).toHaveBeenLastCalledWith(212)
  })

  it('takes a larger step when shift is held', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(220)

    resizer.focus()
    await user.keyboard('{Shift>}{ArrowRight}{/Shift}')
    expect(onChange).toHaveBeenLastCalledWith(252)
  })

  it('clamps to the minimum rather than becoming unusable', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(182)

    resizer.focus()
    await user.keyboard('{ArrowLeft}')
    expect(onChange).toHaveBeenLastCalledWith(180)
  })

  it('clamps to the maximum', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(418)

    resizer.focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith(420)
  })

  it('restores the default width in a single gesture', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(400)

    await user.dblClick(resizer)
    expect(onChange).toHaveBeenLastCalledWith(220)
  })

  it('gives text selection back to the page if it unmounts mid-drag', () => {
    // A drag suspends selection on the whole body. A pane closed during one never receives the
    // pointerup, and every page stayed unselectable after it.
    const { unmount } = render(
      <PaneResizer width={220} onChange={vi.fn()} defaultWidth={220} min={180} max={420} label="Other pane" />,
    )
    fireEvent.pointerDown(screen.getByRole('separator', { name: 'Other pane' }), { pointerId: 1 })
    expect(document.body.style.userSelect).toBe('none')

    unmount()
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('ends the drag when pointer capture is taken away', () => {
    const { resizer } = setup(220)
    fireEvent.pointerDown(resizer, { pointerId: 1 })
    expect(document.body.style.userSelect).toBe('none')

    fireEvent(resizer, new Event('lostpointercapture', { bubbles: true }))
    expect(document.body.style.userSelect).toBe('')
  })

  it('restores the default width from the keyboard too', async () => {
    const user = userEvent.setup()
    const { onChange, resizer } = setup(400)

    resizer.focus()
    await user.keyboard('{Home}')
    expect(onChange).toHaveBeenLastCalledWith(220)
  })
})
