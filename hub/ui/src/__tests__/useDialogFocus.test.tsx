import { renderHook } from '@testing-library/react'
import { createRef } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDialogFocus } from '@/hooks/useDialogFocus'

// F309/F310: a panel opened over another panel must dismiss only itself. The hook's Escape branch
// is a bubble-phase listener on `document`, so it is structurally the last handler to see the key;
// a nested owner that has already answered says so by calling preventDefault(). These cases assert
// the hook reads that flag — nothing here claims to reproduce the browser defect, which depends on
// real focus and real event phases (tasks.md 6.4). The acceptance evidence is the drive.

const mounted: HTMLElement[] = []

function mountPanel() {
  const panel = document.createElement('div')
  const inner = document.createElement('button')
  panel.appendChild(inner)
  document.body.appendChild(panel)
  mounted.push(panel)
  return { panel, inner }
}

function escapeEvent() {
  return new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
}

afterEach(() => {
  mounted.splice(0).forEach((el) => el.remove())
})

describe('useDialogFocus — Escape', () => {
  it('stands down when something nearer has already answered the key', () => {
    const { panel, inner } = mountPanel()
    const panelRef = createRef<HTMLElement>()
    ;(panelRef as { current: HTMLElement | null }).current = panel
    const onClose = vi.fn()
    renderHook(() => useDialogFocus(true, panelRef, onClose))

    // The nested owner: a handler on an element inside the panel that claims the key first.
    inner.addEventListener('keydown', (event) => event.preventDefault())
    inner.dispatchEvent(escapeEvent())

    expect(onClose).not.toHaveBeenCalled()
  })

  it('answers an Escape that nothing nearer has claimed', () => {
    const { panel, inner } = mountPanel()
    const panelRef = createRef<HTMLElement>()
    ;(panelRef as { current: HTMLElement | null }).current = panel
    const onClose = vi.fn()
    renderHook(() => useDialogFocus(true, panelRef, onClose))

    const event = escapeEvent()
    inner.dispatchEvent(event)

    expect(onClose).toHaveBeenCalledTimes(1)
    // And it claims the key on the way out, so an outer dialog using the same hook stands down.
    expect(event.defaultPrevented).toBe(true)
  })
})
