import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { AgentSummary } from '@/api/agents'
import {
  CONVERSATION_DEFAULT_WIDTH,
  CONVERSATION_MIN_WIDTH,
  CONVERSATION_STORAGE_MAX,
  DEFAULT_SPEC_PREFERENCES,
  SPEC_DOC_MIN_WIDTH,
  SPEC_PREFERENCES_KEY,
  loadSpecPreferences,
  saveSpecPreferences,
} from '@/components/spec/specPreferences'

vi.mock('@/hooks/useSSE', () => ({
  // The rail's live dot reads this; a whole-module mock has to carry it or Sidebar throws.
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const HOME = 'spec/spec.html'

// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({
    data: {
      specs: [{ path: HOME, title: 'Specification', kind: 'baseline', state: 'filed', parent: null, order: 0 }],
      home: HOME,
      diagnostics: [],
      missing: [],
    },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: { path: HOME, content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: () => <div data-testid="conversation-surface" />,
}))

import { ConversationView, DOCUMENT_COLUMN_BREAKPOINT } from '@/components/agents/ConversationView'
import { usePanelTabsStore } from '@/store/panelTabsStore'

const PROJECT_ID = 'proj-workspace-test'

// The global stub never fires. Capture the callbacks so a test can report a width and drive the
// real layout-selection path.
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
let queryClient: QueryClient

const agent: AgentSummary = {
  name: 'spec',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  usePanelTabsStore.setState({ projects: {} })
  observers = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ControllableResizeObserver
})

afterEach(() => {
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = original
})

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

function renderView(document: string | null = HOME) {
  const onOpenDocument = vi.fn()
  const utils = render(
    withQueryClient(
      <ConversationView
        agent={agent}
        conversationId="conv-1"
        projectId={PROJECT_ID}
        document={document}
        onSelectConversation={() => {}}
        onOpenDocument={onOpenDocument}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
      />,
    ),
  )
  return { ...utils, onOpenDocument }
}

function resizer() {
  return screen.getByTestId('pane-resizer')
}

describe('conversation workspace — proportions', () => {
  it('gives the conversation the whole width when no document is open', () => {
    renderView(null)
    reportWidth(1600)

    expect(screen.getByTestId('conversation-workspace')).toHaveAttribute('data-layout', 'full')
    expect(screen.getByTestId('conversation-pane')).not.toHaveStyle({
      width: `${CONVERSATION_DEFAULT_WIDTH}px`,
    })
    expect(screen.queryAllByTestId('pane-resizer')).toHaveLength(0)
  })

  it('sizes the conversation to its default and gives the document the rest', () => {
    renderView()
    reportWidth(1600)

    expect(screen.getByTestId('conversation-workspace')).toHaveAttribute('data-layout', 'column')
    expect(screen.getByTestId('conversation-pane')).toHaveStyle({
      width: `${CONVERSATION_DEFAULT_WIDTH}px`,
    })
    // The document takes the remainder and never less than its own minimum. It is the *default*
    // that leaves the document more room, not a rule — the operator can drag past it either way.
    expect(screen.getByTestId('document-pane')).toHaveStyle({ minWidth: `${SPEC_DOC_MIN_WIDTH}px` })
    expect(1600 - CONVERSATION_DEFAULT_WIDTH).toBeGreaterThan(CONVERSATION_DEFAULT_WIDTH)
  })

  it('keeps both minimums inside the breakpoint it derives', () => {
    // Derived from what has to fit, so changing either minimum cannot leave the breakpoint and
    // the layout disagreeing.
    expect(CONVERSATION_MIN_WIDTH + SPEC_DOC_MIN_WIDTH).toBeLessThanOrEqual(
      DOCUMENT_COLUMN_BREAKPOINT,
    )
  })

  it('restores a stored width, which is what makes the control work', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 520 })
    renderView()
    reportWidth(1600)

    expect(screen.getByTestId('conversation-pane')).toHaveStyle({ width: '520px' })
  })

  it('never lets the conversation squeeze the document below its minimum', () => {
    renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT)

    const max = Number(resizer().getAttribute('aria-valuemax'))
    expect(max).toBe(CONVERSATION_MIN_WIDTH)
    expect(max + SPEC_DOC_MIN_WIDTH).toBeLessThanOrEqual(DOCUMENT_COLUMN_BREAKPOINT)
  })

  it('caps the conversation only by the measurement, never by a design maximum', () => {
    // The first version capped it at 560, which made the document panel impossible to shrink.
    // The ceiling is now whatever is left once the document has its minimum, and nothing else.
    renderView()
    reportWidth(2400)

    const max = Number(resizer().getAttribute('aria-valuemax'))
    expect(max).toBe(2400 - SPEC_DOC_MIN_WIDTH - 1)
    expect(max).toBeGreaterThan(CONVERSATION_DEFAULT_WIDTH * 2)
  })

  it('lets the operator drag the conversation past half the width', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 1600 })
    renderView()
    reportWidth(2400)

    expect(screen.getByTestId('conversation-pane')).toHaveStyle({ width: '1600px' })
    // ...and the document keeps its floor rather than vanishing.
    expect(screen.getByTestId('document-pane')).toHaveStyle({ minWidth: `${SPEC_DOC_MIN_WIDTH}px` })
  })

  it('clamps a stored width that no longer fits, without discarding it', () => {
    // A width chosen on a wide window, now shown on a narrow one. The pane shrinks to fit; the
    // preference is untouched, so widening the window restores what the operator chose.
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 1200 })
    renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT)

    const rendered = Number(
      (screen.getByTestId('conversation-pane') as HTMLElement).style.width.replace('px', ''),
    )
    expect(rendered).toBeLessThan(1200)
    expect(rendered).toBeGreaterThanOrEqual(CONVERSATION_MIN_WIDTH)
    expect(loadSpecPreferences().conversationWidth).toBe(1200)
  })

  it('resizes from the keyboard and persists the result', () => {
    renderView()
    reportWidth(1600)

    expect(resizer()).toHaveAttribute('aria-label', 'Resize conversation')
    expect(resizer()).toHaveAttribute('aria-valuenow', String(CONVERSATION_DEFAULT_WIDTH))

    // The conversation is the left pane, so ArrowRight makes it wider.
    fireEvent.keyDown(resizer(), { key: 'ArrowRight' })
    expect(loadSpecPreferences().conversationWidth).toBe(CONVERSATION_DEFAULT_WIDTH + 8)
  })

  it('restores the default width on double-click', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 540 })
    renderView()
    reportWidth(1600)

    fireEvent.dblClick(resizer())
    expect(loadSpecPreferences().conversationWidth).toBe(CONVERSATION_DEFAULT_WIDTH)
  })

  it('ignores a zero-width measurement instead of collapsing to the overlay', () => {
    renderView()
    reportWidth(0)
    expect(screen.getByTestId('conversation-workspace')).toHaveAttribute('data-layout', 'column')
  })
})

describe('conversation workspace — the overlay below the fit threshold', () => {
  it('keeps two columns at exactly the breakpoint', () => {
    renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT)
    expect(screen.getByTestId('conversation-workspace')).toHaveAttribute('data-layout', 'column')
    expect(screen.getByTestId('document-pane')).toBeInTheDocument()
  })

  it('becomes an overlay one pixel below it', async () => {
    renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT - 1)

    expect(screen.getByTestId('conversation-workspace')).toHaveAttribute('data-layout', 'overlay')
    expect(screen.queryByTestId('document-pane')).not.toBeInTheDocument()
    expect(screen.queryAllByTestId('pane-resizer')).toHaveLength(0)
    // The conversation stays usable, and the document is still reachable.
    expect(screen.getByTestId('conversation-surface')).toBeInTheDocument()
    expect(await screen.findByTestId('workspace-drawer')).toBeInTheDocument()
  })

  it('traps focus, closes on Escape, and returns focus to the opener', async () => {
    const user = userEvent.setup()
    renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT - 1)

    const dialog = await screen.findByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('workspace-drawer')).not.toBeInTheDocument())

    // The document is still open in the destination — dismissing the overlay is not closing the
    // document — so the control that reopens it is where focus lands.
    const trigger = screen.getByTestId('conversation-open-document')
    await waitFor(() => expect(trigger).toHaveFocus())

    await user.click(trigger)
    expect(await screen.findByTestId('workspace-drawer')).toBeInTheDocument()
  })

  it('closes the document itself from the overlay bar', async () => {
    const { onOpenDocument } = renderView()
    reportWidth(DOCUMENT_COLUMN_BREAKPOINT - 1)
    await screen.findByTestId('workspace-drawer')

    fireEvent.click(screen.getByTestId('conversation-close-document'))
    expect(onOpenDocument).toHaveBeenCalledWith(null)
  })
})

describe('spec preferences — bounded persistence (FR-10)', () => {
  it('returns defaults when nothing is stored', () => {
    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
  })

  it('round-trips a valid width', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 500 })
    expect(loadSpecPreferences()).toEqual({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 500 })
  })

  it('clamps a stored width into a sane range on the way in and on the way out', () => {
    saveSpecPreferences({ ...DEFAULT_SPEC_PREFERENCES, conversationWidth: 5 })
    expect(loadSpecPreferences().conversationWidth).toBe(CONVERSATION_MIN_WIDTH)

    // Hand-edited storage, never written by the app. The upper bound is a sanity bound, not a
    // design cap — the real ceiling is the measurement, applied at render time.
    localStorage.setItem(SPEC_PREFERENCES_KEY, JSON.stringify({ conversationWidth: 99999 }))
    expect(loadSpecPreferences().conversationWidth).toBe(CONVERSATION_STORAGE_MAX)
  })

  it('rejects a width that is a number but not a measurement', () => {
    // NaN and Infinity are numbers to `typeof`, and both survive a clamp as themselves.
    for (const bad of [NaN, Infinity, -Infinity]) {
      localStorage.setItem(SPEC_PREFERENCES_KEY, JSON.stringify({ conversationWidth: bad }))
      expect(loadSpecPreferences().conversationWidth).toBe(
        DEFAULT_SPEC_PREFERENCES.conversationWidth,
      )
    }
  })

  it('resets corrupt JSON to defaults', () => {
    localStorage.setItem(SPEC_PREFERENCES_KEY, '{not json')
    expect(loadSpecPreferences()).toEqual(DEFAULT_SPEC_PREFERENCES)
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
      conversationWidth: 500,
      // Extra fields must not survive the write.
      apiKey: 'aw_live_SECRET',
      documentContent: '<html>secret</html>',
    } as never)

    const stored = JSON.parse(localStorage.getItem(SPEC_PREFERENCES_KEY) as string)
    expect(Object.keys(stored)).toEqual(['conversationWidth'])
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
