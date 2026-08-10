import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

/* The Spec screen is the specification on its own.
 *
 * It is not the page that was deleted: that one had a navigator, a document *and* a chat in three
 * columns and collapsed the Hub rail to make room. Working on a specification with an agent is the
 * conversation view's job, reached from the composer's Spec pill. This is the other half — the
 * document and the folder tree that chooses one, and nothing else (operator: "just to focus on
 * spec").
 */

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const HOME = 'spec/spec.html'
const CHANGE = 'spec/changes/queued-message-delivery/spec.html'

let listResult: {
  data: {
    specs: { path: string; title?: string; kind?: string; state?: string; parent?: string | null; order?: number }[]
    home: string | null
    diagnostics: unknown[]
    missing: unknown[]
  } | undefined
  isLoading: boolean
  refetch: () => void
}

vi.mock('@/api/spec', () => ({
  useSpecList: () => listResult,
  useSpec: () => ({ data: { path: HOME, content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

import { SpecPage } from '@/components/spec/SpecPage'

let queryClient: QueryClient

function renderPage(document: string | null) {
  const onOpenDocument = vi.fn()
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <SpecPage document={document} onOpenDocument={onOpenDocument} />
    </QueryClientProvider> as ReactNode,
  )
  return { ...utils, onOpenDocument }
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  listResult = {
    data: {
      specs: [
        { path: HOME, title: 'Specification', kind: 'baseline', state: 'filed', parent: null, order: 0 },
        { path: CHANGE, title: 'Queued message delivery', kind: 'change-spec', state: 'filed', parent: null, order: 10 },
      ],
      home: HOME,
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

describe('the Spec screen', () => {
  it('shows the folder tree and the document, and no conversation', () => {
    renderPage(HOME)
    expect(screen.getByTestId('spec-page-tree')).toBeInTheDocument()
    expect(screen.getByTestId('spec-document-panel')).toBeInTheDocument()
    expect(screen.getByTestId(`spec-tree-document-${CHANGE}`)).toBeInTheDocument()

    // The whole point of the screen: nothing to be beside.
    expect(screen.queryByTestId('conversation-header')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByTestId('composer-spec-control')).not.toBeInTheDocument()
  })

  it('offers no close control, because there is nothing behind the panel', () => {
    renderPage(HOME)
    expect(screen.queryByTestId('spec-document-close')).not.toBeInTheDocument()
  })

  it('resolves to the manifest home when the destination names no document', async () => {
    const { onOpenDocument } = renderPage(null)
    await waitFor(() => expect(onOpenDocument).toHaveBeenCalledWith(HOME))
  })

  it('opens a document from the tree', () => {
    const { onOpenDocument } = renderPage(HOME)
    fireEvent.click(screen.getByTestId(`spec-tree-document-${CHANGE}`))
    expect(onOpenDocument).toHaveBeenCalledWith(CHANGE)
  })

  it('marks the open document in the tree', () => {
    renderPage(CHANGE)
    expect(screen.getByTestId(`spec-tree-document-${CHANGE}`)).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTestId(`spec-tree-document-${HOME}`)).not.toHaveAttribute('aria-current')
  })

  it('sizes its navigation column, and remembers it', () => {
    renderPage(HOME)
    const resizer = screen.getByTestId('pane-resizer')
    expect(resizer).toHaveAttribute('aria-label', 'Resize document navigation')

    fireEvent.keyDown(resizer, { key: 'ArrowRight' })
    // Persisted separately from the conversation width: they size different things on different
    // screens, and one number for both would move a column the operator was not looking at.
    const stored = JSON.parse(localStorage.getItem('aw.spec.presentation.v1') as string)
    expect(stored.treeWidth).toBe(288)
    expect(stored.conversationWidth).toBe(480)
  })

  it('says so when the project has no specification at all', () => {
    listResult = { data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }
    renderPage(null)
    expect(screen.getByText('No specification yet')).toBeInTheDocument()
    expect(screen.queryByTestId('spec-page-tree')).not.toBeInTheDocument()
  })

  it('opens the picker with Ctrl+K from here too', async () => {
    renderPage(HOME)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog')).toHaveAccessibleName('Search documents')
  })
})
