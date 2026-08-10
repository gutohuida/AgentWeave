import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { SPEC_BRIDGE_CHANNEL, SPEC_BRIDGE_VERSION } from '@/components/spec/specBridge'
import type { AgentSummary } from '@/api/agents'

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const ROADMAP = 'spec/roadmaps/agentweave-reconstruction.html'
const CHANGE = 'spec/changes/add-spec-navigation/spec.html'
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

// The conversation is the whole agent surface, covered by its own suites. Stubbed so these
// assertions stay about the document panel rather than about every api module that surface reads.
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: () => <div data-testid="conversation-surface" />,
}))

vi.mock('@/api/client', () => ({ fetchWithAuth: vi.fn() }))

import { ConversationView } from '@/components/agents/ConversationView'

let queryClient: QueryClient
let openedDocuments: (string | null)[]

const agent: AgentSummary = {
  name: 'spec',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

/** The document is a property of the destination, so a test opens one by rendering with it —
 *  exactly as `App.tsx` does after a navigation. */
function renderView(document: string | null = ROADMAP) {
  return render(
    withQueryClient(
      <ConversationView
        agent={agent}
        conversationId="conv-1"
        document={document}
        onSelectConversation={() => {}}
        onOpenDocument={(path) => openedDocuments.push(path)}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
      />,
    ),
  )
}

beforeEach(() => {
  cleanup()
  openedDocuments = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  specListResult = {
    data: {
      specs: [
        { path: ROADMAP, title: 'Reconstruction', kind: 'roadmap', state: 'filed', parent: null, order: 30 },
        {
          path: CHANGE,
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

describe('the document panel opens beside the conversation', () => {
  it('shows the conversation alone when no document is open', () => {
    renderView(null)
    expect(screen.getByTestId('conversation-surface')).toBeInTheDocument()
    expect(screen.queryByTestId('spec-document-panel')).not.toBeInTheDocument()
    // "no specification navigation remains on screen" — there is no second rail to leave behind.
    expect(screen.queryByTestId('spec-document-list')).not.toBeInTheDocument()
  })

  it('shows both when the destination names a document', () => {
    renderView()
    expect(screen.getByTestId('conversation-surface')).toBeInTheDocument()
    expect(screen.getByTestId('spec-document-panel')).toBeInTheDocument()
    expect(screen.getByTestId('spec-document-breadcrumb')).toHaveTextContent('Reconstruction')
  })

  it('closing the panel asks the destination to drop the document', () => {
    renderView()
    fireEvent.click(screen.getByTestId('spec-document-close'))
    expect(openedDocuments).toEqual([null])
  })

  it('marks an opened archived document as archived', () => {
    renderView()
    expect(screen.queryByTestId('spec-archived-marker')).not.toBeInTheDocument()

    cleanup()
    renderView(ARCHIVED)
    expect(screen.getByTestId('spec-archived-marker')).toHaveTextContent('Archived')
    expect(screen.getByTestId('spec-archived-marker')).toHaveTextContent('2026-07-29')
  })
})

describe('outline and link routing (FR-5, FR-6, FR-7)', () => {
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

  it('offers the outline only once the document reports a usable TOC', async () => {
    renderView()
    expect(screen.queryByTestId('spec-outline-toggle')).not.toBeInTheDocument()

    postFromFrame(toc)

    fireEvent.click(await screen.findByTestId('spec-outline-toggle'))
    const outline = within(screen.getByTestId('spec-outline'))
    expect(outline.getByText('Summary')).toBeInTheDocument()
    expect(outline.getByText('Requirements')).toBeInTheDocument()
  })

  it('shows no outline when the document has no usable TOC', () => {
    renderView()
    // A document with no nav.toc simply never posts toc-ready.
    expect(screen.queryByTestId('spec-outline-toggle')).not.toBeInTheDocument()
    expect(screen.queryByTestId('spec-outline')).not.toBeInTheDocument()
  })

  it('ignores a message from a window that is not the active frame', () => {
    renderView()
    postFromFrame(toc, true)
    expect(screen.queryByTestId('spec-outline-toggle')).not.toBeInTheDocument()
  })

  it('tracks the active section reported by the document', async () => {
    renderView()
    postFromFrame(toc)
    fireEvent.click(await screen.findByTestId('spec-outline-toggle'))

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
        'true',
      )
    })
  })

  it('routes a valid relative cross-document link through the destination', async () => {
    renderView()
    // The manifest home (the roadmap) is what is open, so the link resolves relative to
    // spec/roadmaps/.
    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'navigate',
      href: '../changes/add-spec-navigation/spec.html#requirements',
    })

    await waitFor(() => expect(openedDocuments).toEqual([CHANGE]))
    expect(screen.queryByTestId('spec-nav-status')).not.toBeInTheDocument()
  })

  it('keeps the current document and explains an unresolved link', async () => {
    renderView()
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
    expect(openedDocuments).toEqual([])

    fireEvent.click(screen.getByLabelText('Dismiss navigation message'))
    await waitFor(() => expect(screen.queryByTestId('spec-nav-status')).not.toBeInTheDocument())
  })

  it('explains a link to a document that is not in the inventory', async () => {
    renderView()
    postFromFrame({
      channel: SPEC_BRIDGE_CHANNEL,
      version: SPEC_BRIDGE_VERSION,
      type: 'navigate',
      href: '../ghost/spec.html',
    })
    expect(await screen.findByTestId('spec-nav-status')).toHaveTextContent(/not in the current/i)
  })

  /* Task 5.4. A layout change is exactly the kind of work that quietly relaxes a security
   * boundary for convenience, so the frame's terms are asserted where the frame now lives. */
  it('keeps the sandbox opaque in its new container', () => {
    renderView()
    const sandbox = screen.getByTestId('spec-frame').getAttribute('sandbox')
    expect(sandbox).toBe('allow-scripts')
    expect(sandbox).not.toContain('allow-same-origin')
  })
})

describe('document search (FR-3, FR-9)', () => {
  it('opens from the breadcrumb, closes on Escape, and returns focus', async () => {
    const user = userEvent.setup()
    renderView()

    const breadcrumb = screen.getByTestId('spec-document-breadcrumb')
    await user.click(breadcrumb)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleDescription(
      'Search current and archived specification documents by title, path, or change name.',
    )
    expect(within(dialog).getByLabelText('Search documents')).toHaveFocus()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(breadcrumb).toHaveFocus())
  })

  it('opens from Ctrl+K in a conversation with no document open at all', async () => {
    renderView(null)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('opens from the Cmd+K shortcut', async () => {
    renderView()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('groups archived matches after current ones and disables missing matches', async () => {
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html', title: 'Add Gone Change' }]
    const user = userEvent.setup()
    renderView()

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

  it('choosing a result opens it in the destination, archives included', async () => {
    const user = userEvent.setup()
    renderView()

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /Add Agent Stream Kinds/ }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(openedDocuments).toEqual([ARCHIVED])
  })
})
