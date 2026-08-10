import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { SPEC_BRIDGE_CHANNEL, SPEC_BRIDGE_VERSION } from '@/components/spec/specBridge'

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const ROADMAP = 'spec/roadmaps/agentweave-reconstruction.html'
const ARCHIVED = 'spec/changes/archive/2026-07-29-add-agent-stream-kinds/spec.html'

let specListResult: {
  data: {
    specs: { path: string; state?: string; title?: string; kind?: string; parent?: string | null; order?: number }[]
    home: string | null
    diagnostics: unknown[]
    missing: { path: string; title?: string }[]
  }
  isLoading: boolean
  refetch: () => void
}

vi.mock('@/api/spec', () => ({
  useSpecList: () => specListResult,
  useSpec: () => ({ data: { path: 'x', content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'spec', status: 'idle' }] }),
}))

// The chat pane is now the whole conversation surface, covered by its own suite
// (`specChatSurface.test.tsx`). Stubbed so these assertions stay about navigation rather than
// about every api module the conversation surface reads.
vi.mock('@/components/spec/SpecChat', () => ({
  SpecChat: () => <div data-testid="spec-chat" />,
}))

vi.mock('@/api/client', () => ({ fetchWithAuth: vi.fn() }))

import { SpecPage } from '@/components/spec/SpecPage'

let queryClient: QueryClient

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

beforeEach(() => {
  cleanup()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  specListResult = {
    data: {
      specs: [
        { path: ROADMAP, title: 'Reconstruction', kind: 'roadmap', state: 'filed', parent: null, order: 30 },
        {
          path: 'spec/changes/add-spec-navigation/spec.html',
          title: 'Add Spec Navigation',
          kind: 'change-spec',
          state: 'filed',
          parent: ROADMAP,
          order: 10,
        },
        {
          path: ARCHIVED,
          title: 'Add Agent Stream Kinds',
          kind: 'change-spec',
          state: 'filed',
          parent: ROADMAP,
          order: 10,
        },
      ],
      home: ROADMAP,
      diagnostics: [],
      missing: [],
    },
    isLoading: false,
    refetch: () => {},
  }
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
    mode: 'light',
  })
})

describe('Spec page — library and history (FR-1, FR-2)', () => {
  it('shows current documents in the library and hides archives from it', () => {
    render(withQueryClient(<SpecPage />))
    const list = within(screen.getByTestId('spec-document-list'))

    expect(list.getByText('Reconstruction')).toBeInTheDocument()
    expect(list.getByText('Add Spec Navigation')).toBeInTheDocument()
    expect(list.queryByText('Add Agent Stream Kinds')).not.toBeInTheDocument()
  })

  it('reveals archived changes only after History is activated', () => {
    render(withQueryClient(<SpecPage />))
    fireEvent.click(screen.getByRole('tab', { name: 'History' }))

    const list = within(screen.getByTestId('spec-document-list'))
    expect(list.getByText('Add Agent Stream Kinds')).toBeInTheDocument()
    expect(list.getByText('Reconstruction')).toBeInTheDocument() // the group label
    expect(list.queryByText('Add Spec Navigation')).not.toBeInTheDocument()
  })

  it('marks an opened archived document as archived', () => {
    render(withQueryClient(<SpecPage />))
    expect(screen.queryByTestId('spec-archived-marker')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'History' }))
    fireEvent.click(screen.getByText('Add Agent Stream Kinds'))

    expect(screen.getByTestId('spec-archived-marker')).toHaveTextContent('Archived')
    expect(screen.getByTestId('spec-archived-marker')).toHaveTextContent('2026-07-29')
  })

  it('keeps missing manifest entries visible but not selectable', () => {
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html', title: 'Gone Change' }]
    render(withQueryClient(<SpecPage />))

    const attention = within(screen.getByTestId('spec-needs-attention'))
    expect(attention.getByText('Gone Change')).toBeInTheDocument()
    // rendered as a non-button so it cannot be opened
    expect(attention.queryByRole('button', { name: /Gone Change/ })).not.toBeInTheDocument()
  })
})

describe('Spec page — outline and link routing (FR-5, FR-6, FR-7)', () => {
  function postFromFrame(data: unknown, useForeignSource = false) {
    const frame = screen.getByTestId('spec-frame') as HTMLIFrameElement
    const event = new MessageEvent('message', {
      data,
      source: useForeignSource ? window : frame.contentWindow,
    })
    fireEvent(window, event)
  }

  const toc = {
    channel: SPEC_BRIDGE_CHANNEL,
    version: SPEC_BRIDGE_VERSION,
    type: 'toc-ready',
    anchors: [
      { id: 'summary', label: 'Summary' },
      { id: 'requirements', label: 'Requirements' },
    ],
  }

  it('renders the shell outline once the document reports a usable TOC', async () => {
    render(withQueryClient(<SpecPage />))
    expect(screen.queryByTestId('spec-outline')).not.toBeInTheDocument()

    postFromFrame(toc)

    const outline = within(await screen.findByTestId('spec-outline'))
    expect(outline.getByText('Summary')).toBeInTheDocument()
    expect(outline.getByText('Requirements')).toBeInTheDocument()
  })

  it('shows no outline when the document has no usable TOC', () => {
    render(withQueryClient(<SpecPage />))
    // A document with no nav.toc simply never posts toc-ready.
    expect(screen.queryByTestId('spec-outline')).not.toBeInTheDocument()
  })

  it('ignores a message from a window that is not the active frame', () => {
    render(withQueryClient(<SpecPage />))
    postFromFrame(toc, true)
    expect(screen.queryByTestId('spec-outline')).not.toBeInTheDocument()
  })

  it('tracks the active section reported by the document', async () => {
    render(withQueryClient(<SpecPage />))
    postFromFrame(toc)
    await screen.findByTestId('spec-outline')

    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'active-section',
      id: 'requirements',
    })

    await waitFor(() => {
      const outline = within(screen.getByTestId('spec-outline'))
      expect(outline.getByText('Requirements').closest('button')).toHaveAttribute(
        'aria-current',
        'true'
      )
    })
  })

  it('routes a valid relative cross-document link through the shell', async () => {
    render(withQueryClient(<SpecPage />))
    // The manifest home (the roadmap) is what opens first, so the link is
    // resolved relative to spec/roadmaps/.
    const change = 'spec/changes/add-spec-navigation/spec.html'
    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'navigate',
      href: '../changes/add-spec-navigation/spec.html#requirements',
    })

    await waitFor(() => {
      const list = within(screen.getByTestId('spec-document-list'))
      expect(list.getByTitle(change)).toHaveAttribute('aria-current', 'true')
    })
    expect(screen.queryByTestId('spec-nav-status')).not.toBeInTheDocument()
  })

  it('keeps the current document and explains an unresolved link', async () => {
    render(withQueryClient(<SpecPage />))
    const before = screen.getByTestId('spec-frame').getAttribute('title')

    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'navigate',
      href: 'https://example.com/elsewhere.html',
    })

    const status = await screen.findByTestId('spec-nav-status')
    expect(status).toHaveTextContent(/outside the specification/i)
    expect(status).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByTestId('spec-frame')).toHaveAttribute('title', before as string)

    fireEvent.click(screen.getByLabelText('Dismiss navigation message'))
    await waitFor(() => expect(screen.queryByTestId('spec-nav-status')).not.toBeInTheDocument())
  })

  it('explains a link to a document that is not in the inventory', async () => {
    render(withQueryClient(<SpecPage />))
    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'navigate',
      href: '../ghost/spec.html',
    })
    expect(await screen.findByTestId('spec-nav-status')).toHaveTextContent(/not in the current/i)
  })

  it('keeps the sandbox opaque', () => {
    render(withQueryClient(<SpecPage />))
    const sandbox = screen.getByTestId('spec-frame').getAttribute('sandbox')
    expect(sandbox).toBe('allow-scripts')
    expect(sandbox).not.toContain('allow-same-origin')
  })
})

describe('Spec page — document search (FR-3, FR-9)', () => {
  it('opens with Ctrl+K, closes on Escape, and returns focus', async () => {
    const user = userEvent.setup()
    render(withQueryClient(<SpecPage />))

    const searchButton = screen.getByRole('button', { name: /Search documents/ })
    await user.click(searchButton)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleDescription(
      'Search current and archived specification documents by title, path, or change name.'
    )
    expect(within(dialog).getByLabelText('Search documents')).toHaveFocus()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(searchButton).toHaveFocus())
  })

  it('opens from the Ctrl+K shortcut anywhere on the page', async () => {
    render(withQueryClient(<SpecPage />))
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('opens from the Cmd+K shortcut', async () => {
    render(withQueryClient(<SpecPage />))
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('groups archived matches after current ones and disables missing matches', async () => {
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html', title: 'Add Gone Change' }]
    const user = userEvent.setup()
    render(withQueryClient(<SpecPage />))

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Search documents'), 'add')

    expect(within(dialog).getByText('Archived')).toBeInTheDocument()
    expect(within(dialog).getByText('Missing')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /Add Gone Change/ })).toBeDisabled()

    const buttons = within(dialog).getAllByRole('button')
    const labels = buttons.map((b) => b.textContent ?? '')
    const currentIndex = labels.findIndex((l) => l.includes('Add Spec Navigation'))
    const archivedIndex = labels.findIndex((l) => l.includes('Add Agent Stream Kinds'))
    expect(currentIndex).toBeGreaterThanOrEqual(0)
    expect(archivedIndex).toBeGreaterThan(currentIndex)
  })

  it('selecting an archived result switches the browser to History', async () => {
    const user = userEvent.setup()
    render(withQueryClient(<SpecPage />))

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /Add Agent Stream Kinds/ }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('spec-archived-marker')).toBeInTheDocument()
  })
})
