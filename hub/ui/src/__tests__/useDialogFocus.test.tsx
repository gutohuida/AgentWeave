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

// F307: measured in a real browser, the first Tab in a confirm-only dialog left the panel for the
// control behind the scrim, because focus was still on the trigger and the hook only wrapped Tab at
// the panel's own first and last controls.
describe('useDialogFocus — the first Tab (F307)', () => {
  function mountDialog() {
    const trigger = document.createElement('button')
    trigger.textContent = 'Save'
    const behind = document.createElement('textarea')
    const panel = document.createElement('div')
    const cancel = document.createElement('button')
    cancel.textContent = 'Cancel'
    const confirm = document.createElement('button')
    confirm.textContent = 'Confirm'
    panel.append(cancel, confirm)
    document.body.append(trigger, behind, panel)
    mounted.push(trigger, behind, panel)
    const panelRef = createRef<HTMLElement>()
    ;(panelRef as { current: HTMLElement | null }).current = panel
    return { trigger, panel, cancel, confirm, panelRef }
  }

  function tab(shiftKey = false) {
    const event = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })
    ;(document.activeElement ?? document.body).dispatchEvent(event)
    return event
  }

  it('moves a Tab from outside the panel to its first control', () => {
    const { trigger, cancel, panelRef } = mountDialog()
    trigger.focus()
    renderHook(() => useDialogFocus(true, panelRef, vi.fn()))

    const event = tab()

    expect(event.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(cancel)
  })

  it('moves a Shift+Tab from outside the panel to its last control', () => {
    const { trigger, confirm, panelRef } = mountDialog()
    trigger.focus()
    renderHook(() => useDialogFocus(true, panelRef, vi.fn()))

    tab(true)

    expect(document.activeElement).toBe(confirm)
  })

  it('leaves a Tab between controls inside the panel to the browser', () => {
    const { cancel, panelRef } = mountDialog()
    cancel.focus()
    renderHook(() => useDialogFocus(true, panelRef, vi.fn()))

    expect(tab().defaultPrevented).toBe(false)
  })

  it('leaves Tab to the newer of two open dialogs', () => {
    const outer = mountDialog()
    const inner = mountDialog()
    outer.cancel.focus()
    renderHook(() => useDialogFocus(true, outer.panelRef, vi.fn()))
    renderHook(() => useDialogFocus(true, inner.panelRef, vi.fn()))
    inner.cancel.focus()

    // A Tab between the newer dialog's own controls is the browser's to move. The older dialog,
    // which sees focus outside its panel, must not claim it.
    expect(tab().defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(inner.cancel)
  })
})
