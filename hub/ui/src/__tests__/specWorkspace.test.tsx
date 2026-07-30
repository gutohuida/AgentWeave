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

function renderWorkspace(chatCollapsed = false) {
  const onChatCollapsedChange = vi.fn()
  const utils = render(
    <SpecWorkspace
      chatCollapsed={chatCollapsed}
      onChatCollapsedChange={onChatCollapsedChange}
      navigation={<div data-testid="nav-content">Navigation</div>}
      document={<div data-testid="doc-content">Document</div>}
      chat={<div data-testid="chat-content">Chat</div>}
    />
  )
  return { ...utils, onChatCollapsedChange }
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

  it('keeps the fixed panes within the wide budget', () => {
    renderWorkspace()
    reportWidth(SPEC_WIDE_BREAKPOINT)

    expect(screen.getByTestId('spec-nav-pane')).toHaveStyle({ width: `${SPEC_NAV_WIDTH}px` })
    expect(screen.getByTestId('spec-chat-pane')).toHaveStyle({ width: `${SPEC_CHAT_WIDTH}px` })
    expect(screen.getByTestId('spec-document-pane')).toHaveStyle({
      minWidth: `${SPEC_DOC_MIN_WIDTH}px`,
    })
    // The breakpoint measures the workspace, which excludes the Hub rail, so
    // the two panes plus the document minimum must exactly fit within it.
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
    saveSpecPreferences({ chatCollapsed: true, libraryMode: 'history' })
    expect(loadSpecPreferences()).toEqual({ chatCollapsed: true, libraryMode: 'history' })
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
    expect(loadSpecPreferences()).toEqual({ chatCollapsed: true, libraryMode: 'library' })
  })

  it('resets a non-object payload', () => {
    for (const payload of ['[]', '"library"', 'null', '7']) {
      localStorage.setItem(SPEC_PREFERENCES_KEY, payload)
      expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
    }
  })

  it('persists only the two allowed keys, never content or credentials', () => {
    saveSpecPreferences({
      chatCollapsed: true,
      libraryMode: 'history',
      // Extra fields must not survive the write.
      apiKey: 'aw_live_SECRET',
      documentContent: '<html>secret</html>',
    } as never)

    const stored = JSON.parse(localStorage.getItem(SPEC_PREFERENCES_KEY) as string)
    expect(Object.keys(stored).sort()).toEqual(['chatCollapsed', 'libraryMode'])
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
