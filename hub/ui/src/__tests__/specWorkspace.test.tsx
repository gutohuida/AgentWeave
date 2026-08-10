import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  SpecWorkspace,
  SPEC_WIDE_BREAKPOINT,
  SPEC_NAV_WIDTH,
  SPEC_DOC_MIN_WIDTH,
  SPEC_CHAT_WIDTH,
} from '@/components/spec/SpecWorkspace'
import {
  DEFAULT_SPEC_PREFERENCES,
  loadSpecPreferences,
  saveSpecPreferences,
  SPEC_CHAT_MAX_WIDTH,
  SPEC_CHAT_MIN_WIDTH,
  SPEC_NAV_MAX_WIDTH,
  SPEC_NAV_MIN_WIDTH,
  SPEC_PREFERENCES_KEY,
} from '@/components/spec/specPreferences'

// The global stub never fires. Capture the callbacks so a test can report a
// width and drive the real mode-selection path.
type Cb = (entries: { contentRect: { width: number } }[]) => void
let observers: Cb[] = []

class ControllableResizeObserver {
  constructor(private cb: Cb) {
    observers.push(cb)
  }
  observe() {}
  unobserve() {}
  disconnect() {
    observers = observers.filter((c) => c !== this.cb)
  }
}

function reportWidth(width: number) {
  act(() => {
    for (const cb of observers) cb([{ contentRect: { width } }])
  })
}

const original = globalThis.ResizeObserver

beforeEach(() => {
  observers = []
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ControllableResizeObserver
})

afterEach(() => {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original
})

function renderWorkspace(
  chatCollapsed = false,
  widths: { navWidth?: number; chatWidth?: number } = {}
) {
  const onChatCollapsedChange = vi.fn()
  const onNavWidthChange = vi.fn()
  const onChatWidthChange = vi.fn()
  const utils = render(
    <SpecWorkspace
      chatCollapsed={chatCollapsed}
      onChatCollapsedChange={onChatCollapsedChange}
      navWidth={widths.navWidth ?? SPEC_NAV_WIDTH}
      chatWidth={widths.chatWidth ?? SPEC_CHAT_WIDTH}
      onNavWidthChange={onNavWidthChange}
      onChatWidthChange={onChatWidthChange}
      navigation={<div data-testid="nav-content">Navigation</div>}
      document={<div data-testid="doc-content">Document</div>}
      chat={<div data-testid="chat-content">Chat</div>}
    />
  )
  return { ...utils, onChatCollapsedChange, onNavWidthChange, onChatWidthChange }
}

/** The two dividers, in DOM order: navigation first, chat second. */
function resizers() {
  const all = screen.getAllByTestId('pane-resizer')
  return { nav: all[0], chat: all[1] }
}

describe('spec workspace — mode boundary (FR-8)', () => {
  it('uses wide panes at exactly the breakpoint', () => {
    renderWorkspace()
    reportWidth(SPEC_WIDE_BREAKPOINT)

    expect(screen.getByTestId('spec-workspace')).toHaveAttribute('data-mode', 'wide')
    expect(screen.getByTestId('spec-nav-pane')).toBeInTheDocument()
    expect(screen.getByTestId('spec-chat-pane')).toBeInTheDocument()
  })

  it('switches to compact one pixel below the breakpoint', () => {
    renderWorkspace()
    reportWidth(SPEC_WIDE_BREAKPOINT - 1)

    expect(screen.getByTestId('spec-workspace')).toHaveAttribute('data-mode', 'compact')
    // Neither side pane may hold fixed width while the document is narrow.
    expect(screen.queryByTestId('spec-nav-pane')).not.toBeInTheDocument()
    expect(screen.queryByTestId('spec-chat-pane')).not.toBeInTheDocument()
    expect(screen.getByTestId('doc-content')).toBeInTheDocument()
  })

  it('lets the workspace shrink below wide child minimums', () => {
    renderWorkspace()
    expect(screen.getByTestId('spec-workspace')).toHaveClass(
      'min-w-0',
      'w-full',
      'max-w-full',
      'overflow-hidden'
    )
  })

  it('keeps the default panes within the wide budget', () => {
    renderWorkspace()
    reportWidth(SPEC_WIDE_BREAKPOINT)

    expect(screen.getByTestId('spec-nav-pane')).toHaveStyle({ width: `${SPEC_NAV_WIDTH}px` })
    expect(screen.getByTestId('spec-chat-pane')).toHaveStyle({ width: `${SPEC_CHAT_WIDTH}px` })
    expect(screen.getByTestId('spec-document-pane')).toHaveStyle({
      minWidth: `${SPEC_DOC_MIN_WIDTH}px`,
    })
    // The breakpoint measures the workspace, which excludes the Hub rail, so the two panes
    // plus the document minimum — and now the two dividers between them — must fit within it.
    expect(SPEC_NAV_WIDTH + SPEC_DOC_MIN_WIDTH + SPEC_CHAT_WIDTH).toBeLessThanOrEqual(
      SPEC_WIDE_BREAKPOINT
    )
  })

  it('ignores a zero-width measurement instead of collapsing to compact', () => {
    renderWorkspace()
    reportWidth(0)
    expect(screen.getByTestId('spec-workspace')).toHaveAttribute('data-mode', 'wide')
  })

  it('collapses and expands the chat pane through the preference callback', () => {
    const { onChatCollapsedChange } = renderWorkspace(false)
    reportWidth(SPEC_WIDE_BREAKPOINT)

    fireEvent.click(screen.getByLabelText('Collapse chat'))
    expect(onChatCollapsedChange).toHaveBeenCalledWith(true)
  })

  it('hides the chat pane when the preference says collapsed', () => {
    renderWorkspace(true)
    reportWidth(SPEC_WIDE_BREAKPOINT)

    expect(screen.queryByTestId('spec-chat-pane')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Expand chat')).toBeInTheDocument()
  })
})

describe('spec workspace — operator-sized panes', () => {
  it('offers a divider on each boundary in wide mode', () => {
    renderWorkspace()
    reportWidth(1600)

    const all = screen.getAllByTestId('pane-resizer')
    expect(all).toHaveLength(2)
    expect(all[0]).toHaveAttribute('aria-label', 'Resize document navigation')
    expect(all[1]).toHaveAttribute('aria-label', 'Resize chat')
  })

  it('reports the width of the pane it sizes, not the position of the divider', () => {
    renderWorkspace()
    reportWidth(1600)

    expect(resizers().nav).toHaveAttribute('aria-valuenow', String(SPEC_NAV_WIDTH))
    expect(resizers().chat).toHaveAttribute('aria-valuenow', String(SPEC_CHAT_WIDTH))
  })

  it('resizes each pane from the keyboard, in the direction the pane grows', () => {
    const { onNavWidthChange, onChatWidthChange } = renderWorkspace()
    reportWidth(1600)

    // Navigation grows rightward.
    fireEvent.keyDown(resizers().nav, { key: 'ArrowRight' })
    expect(onNavWidthChange).toHaveBeenLastCalledWith(SPEC_NAV_WIDTH + 8)

    // The chat pane grows leftward, so ArrowLeft is what makes it wider — the key and the
    // thing on screen have to agree.
    fireEvent.keyDown(resizers().chat, { key: 'ArrowLeft' })
    expect(onChatWidthChange).toHaveBeenLastCalledWith(SPEC_CHAT_WIDTH + 8)
  })

  it('restores a default width on double-click', () => {
    const { onNavWidthChange } = renderWorkspace(false, { navWidth: 400 })
    reportWidth(1600)

    fireEvent.dblClick(resizers().nav)
    expect(onNavWidthChange).toHaveBeenLastCalledWith(SPEC_NAV_WIDTH)
  })

  it('renders the widths it is given', () => {
    renderWorkspace(false, { navWidth: 300, chatWidth: 420 })
    reportWidth(1600)

    expect(screen.getByTestId('spec-nav-pane')).toHaveStyle({ width: '300px' })
    expect(screen.getByTestId('spec-chat-pane')).toHaveStyle({ width: '420px' })
  })

  it('never lets a side pane squeeze the document below its minimum', () => {
    // At the breakpoint the three panes exactly fill the workspace, so navigation has no room
    // to grow at all — its ceiling has to come from the measurement, not from the constant.
    renderWorkspace()
    reportWidth(SPEC_WIDE_BREAKPOINT)

    const navMax = Number(resizers().nav.getAttribute('aria-valuemax'))
    const chatMax = Number(resizers().chat.getAttribute('aria-valuemax'))
    expect(navMax).toBeLessThan(SPEC_NAV_MAX_WIDTH)
    expect(chatMax).toBeLessThan(SPEC_CHAT_MAX_WIDTH)
    expect(navMax + SPEC_DOC_MIN_WIDTH + SPEC_CHAT_WIDTH).toBeLessThanOrEqual(
      SPEC_WIDE_BREAKPOINT
    )
  })

  it('clamps a stored width that no longer fits, without discarding it', () => {
    // A width chosen on a wide window, now shown on a narrow one. The pane shrinks to fit; the
    // preference is untouched, so widening the window restores what the operator chose.
    const { onNavWidthChange } = renderWorkspace(false, { navWidth: SPEC_NAV_MAX_WIDTH })
    reportWidth(SPEC_WIDE_BREAKPOINT)

    const rendered = Number(
      (screen.getByTestId('spec-nav-pane') as HTMLElement).style.width.replace('px', '')
    )
    expect(rendered).toBeLessThan(SPEC_NAV_MAX_WIDTH)
    expect(rendered).toBeGreaterThanOrEqual(SPEC_NAV_MIN_WIDTH)
    expect(onNavWidthChange).not.toHaveBeenCalled()
  })

  it('has no dividers in compact mode, where the drawers do the work', () => {
    renderWorkspace()
    reportWidth(800)
    expect(screen.queryAllByTestId('pane-resizer')).toHaveLength(0)
  })

  it('leaves only the navigation divider when the chat pane is collapsed', () => {
    renderWorkspace(true)
    reportWidth(1600)

    const all = screen.getAllByTestId('pane-resizer')
    expect(all).toHaveLength(1)
    expect(all[0]).toHaveAttribute('aria-label', 'Resize document navigation')
  })
})

describe('spec workspace — compact drawers and focus (FR-9)', () => {
  it('opens navigation in a drawer, closes on Escape, and restores focus', async () => {
    renderWorkspace()
    reportWidth(800)

    // userEvent focuses on pointer-down the way a browser does; fireEvent.click
    // does not, so Radix would have no prior focus to restore.
    const user = userEvent.setup()
    const trigger = screen.getByLabelText('Open documents')
    await user.click(trigger)

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('Documents')
    expect(dialog).toHaveAccessibleDescription(
      'Documents panel for the current specification workspace.'
    )
    expect(screen.getByTestId('nav-content')).toBeInTheDocument()

    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('opens chat in a drawer with an accessible close control', async () => {
    renderWorkspace()
    reportWidth(800)

    fireEvent.click(screen.getByLabelText('Open chat'))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('Chat')
    expect(screen.getByTestId('chat-content')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Close Chat'))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('closes an open drawer when the workspace returns to wide', async () => {
    renderWorkspace()
    reportWidth(800)
    fireEvent.click(screen.getByLabelText('Open documents'))
    await screen.findByRole('dialog')

    reportWidth(SPEC_WIDE_BREAKPOINT)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // and the navigation is back as a fixed pane, not lost
    expect(screen.getByTestId('spec-nav-pane')).toBeInTheDocument()
  })
})

describe('spec preferences — bounded persistence (FR-10)', () => {
  it('returns defaults when nothing is stored', () => {
    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
  })

  it('round-trips valid values', () => {
    saveSpecPreferences({
      chatCollapsed: true,
      libraryMode: 'history',
      navWidth: 300,
      chatWidth: 420,
    })
    expect(loadSpecPreferences()).toEqual({
      chatCollapsed: true,
      libraryMode: 'history',
      navWidth: 300,
      chatWidth: 420,
    })
  })

  it('keeps a pane width across a reload, which is what makes the control work', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, navWidth: 340 })
    expect(loadSpecPreferences().navWidth).toBe(340)
  })

  it('clamps a stored width into its usable range on the way in and on the way out', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, navWidth: 5, chatWidth: 5000 })
    expect(loadSpecPreferences()).toMatchObject({
      navWidth: SPEC_NAV_MIN_WIDTH,
      chatWidth: SPEC_CHAT_MAX_WIDTH,
    })

    // Hand-edited storage, never written by the app.
    localStorage.setItem(
      SPEC_PREFERENCES_KEY,
      JSON.stringify({ ...DEFAULT_SPEC_PREFERENCES, navWidth: 9999, chatWidth: 1 })
    )
    expect(loadSpecPreferences()).toMatchObject({
      navWidth: SPEC_NAV_MAX_WIDTH,
      chatWidth: SPEC_CHAT_MIN_WIDTH,
    })
  })

  it('rejects a width that is a number but not a measurement', () => {
    // NaN and Infinity are numbers to `typeof`, and both survive a clamp as themselves.
    for (const bad of [NaN, Infinity, -Infinity]) {
      localStorage.setItem(
        SPEC_PREFERENCES_KEY,
        JSON.stringify({ ...DEFAULT_SPEC_PREFERENCES, navWidth: bad })
      )
      expect(loadSpecPreferences().navWidth).toBe(DEFAULT_SPEC_PREFERENCES.navWidth)
    }
  })

  it('resets corrupt JSON to defaults', () => {
    localStorage.setItem(SPEC_PREFERENCES_KEY, '{not json')
    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
  })

  it('resets out-of-range and wrongly typed values field by field', () => {
    localStorage.setItem(
      SPEC_PREFERENCES_KEY,
      JSON.stringify({ chatCollapsed: 'yes', libraryMode: 'archive-everything' })
    )
    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)

    localStorage.setItem(
      SPEC_PREFERENCES_KEY,
      JSON.stringify({ chatCollapsed: true, libraryMode: 42 })
    )
    expect(loadSpecPreferences()).toEqual({
      ...DEFAULT_SPEC_PREFERENCES,
      chatCollapsed: true,
      libraryMode: 'library',
    })
  })

  it('resets a non-object payload', () => {
    for (const payload of ['[]', '"library"', 'null', '7']) {
      localStorage.setItem(SPEC_PREFERENCES_KEY, payload)
      expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
    }
  })

  it('persists only the allowed keys, never content or credentials', () => {
    saveSpecPreferences({
      ...DEFAULT_SPEC_PREFERENCES,
      chatCollapsed: true,
      libraryMode: 'history',
      // Extra fields must not survive the write.
      apiKey: 'aw_live_SECRET',
      documentContent: '<html>secret</html>',
    } as never)

    const stored = JSON.parse(localStorage.getItem(SPEC_PREFERENCES_KEY) as string)
    expect(Object.keys(stored).sort()).toEqual([
      'chatCollapsed',
      'chatWidth',
      'libraryMode',
      'navWidth',
    ])
    expect(localStorage.getItem(SPEC_PREFERENCES_KEY)).not.toContain('aw_live_SECRET')
  })

  it('survives storage being unavailable', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })

    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
    expect(() => saveSpecPreferences(DEFAULT_SPEC_PREFERENCES)).not.toThrow()

    getItem.mockRestore()
    setItem.mockRestore()
  })
})
