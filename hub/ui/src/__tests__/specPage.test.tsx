import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
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
    specs: { path: string; title?: string; kind?: string; state?: string; parent?: string | null; order?: number; phase?: string }[]
    home: string | null
    diagnostics: unknown[]
    missing: unknown[]
  } | undefined
  isLoading: boolean
  refetch: () => void
}

// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
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
  it('is the document, and nothing else', () => {
    renderPage(HOME)
    expect(screen.getByTestId('spec-document-panel')).toBeInTheDocument()

    // No conversation — that is the point of the screen.
    expect(screen.queryByTestId('conversation-header')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByTestId('composer-spec-control')).not.toBeInTheDocument()

    // And no navigation column: choosing a document is the rail's job while this screen is open,
    // the way it is Environment's job while that is open (operator: "two navigations are weird").
    expect(screen.queryByTestId('spec-page-tree')).not.toBeInTheDocument()
    expect(screen.queryByTestId(`spec-tree-document-${CHANGE}`)).not.toBeInTheDocument()
    expect(screen.queryByTestId('pane-resizer')).not.toBeInTheDocument()
  })

  it('offers no close control, because there is nothing behind the panel', () => {
    renderPage(HOME)
    expect(screen.queryByTestId('spec-document-close')).not.toBeInTheDocument()
  })

  it('resolves to the manifest home when the destination names no document', async () => {
    const { onOpenDocument } = renderPage(null)
    await waitFor(() => expect(onOpenDocument).toHaveBeenCalledWith(HOME))
  })

  it('opens another document from the breadcrumb picker', async () => {
    const { onOpenDocument } = renderPage(HOME)
    fireEvent.click(screen.getByTestId('spec-document-breadcrumb'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByTestId(`spec-tree-document-${CHANGE}`))
    expect(onOpenDocument).toHaveBeenCalledWith(CHANGE)
  })

  it('says so when the project has no specification at all', () => {
    listResult = { data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }
    renderPage(null)
    expect(screen.getByText('No specification yet')).toBeInTheDocument()
    expect(screen.queryByTestId('spec-page-tree')).not.toBeInTheDocument()
  })

  it('says so, rather than loading forever, when every document is archived', () => {
    // Archiving is a phase transition, not a move, so a project can have documents on disk with
    // none of them resolvable as "current" — resolveSelection then has nothing to hand back, the
    // effect never calls onOpenDocument, and without this branch the screen sat on "Loading…" with
    // no visible way out (Ctrl+K still worked, but nothing on screen said so).
    listResult = {
      data: {
        specs: [{ path: HOME, title: 'Specification', kind: 'baseline', state: 'filed', parent: null, order: 0, phase: 'archived' }],
        home: HOME,
        diagnostics: [],
        missing: [],
      },
      isLoading: false,
      refetch: () => {},
    }
    renderPage(null)
    expect(screen.getByText('Everything here is archived')).toBeInTheDocument()
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument()
  })

  it('opens the picker with Ctrl+K from here too', async () => {
    renderPage(HOME)
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog')).toHaveAccessibleName('Search documents')
  })
})
