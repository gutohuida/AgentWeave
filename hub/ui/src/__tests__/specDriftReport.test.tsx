import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

/* What used to be `specManifestRepair.test.tsx`.
 *
 * The "Repair manifest" button is gone (A1 task 3.5, design.md Decision 4): it composed
 * "Run aw-spec-reindex to repair spec/index.json" and sent it to an agent chosen by a hardcoded
 * name convention, through a second bespoke trigger path, instructing a skill nothing installs.
 * Its three tests went with it. Everything here is about the drift *report*, which stays —
 * showing a condition and offering to act on it are different things, and only the second one
 * was broken.
 */

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

// The chat is the whole conversation surface now, with its own suite
// (`specChatSurface.test.tsx`). Stubbed here so these assertions stay about the drift report
// rather than about every api module the conversation surface reads.
vi.mock('@/components/spec/SpecChat', () => ({
  SpecChat: () => <div data-testid="spec-chat" />,
}))

// Controlled by each test.
let specListResult: {
  data: {
    specs: { path: string; state?: string; title?: string; kind?: string }[]
    home: string | null
    diagnostics: { code: string; path?: string | null; field?: string | null }[]
    missing: { path: string }[]
  }
  isLoading: boolean
  refetch: () => void
}

vi.mock('@/api/spec', () => ({
  useSpecList: () => specListResult,
  useSpec: () => ({ data: { path: 'spec/spec.html', content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'spec', status: 'idle' }] }),
}))

import { SpecPage } from '@/components/spec/SpecPage'

let queryClient: QueryClient

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

describe('Spec tab — manifest drift report', () => {
  beforeEach(() => {
    cleanup()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    specListResult = {
      data: {
        specs: [{ path: 'spec/spec.html', state: 'unindexed' }],
        home: null,
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

  it('shows no drift banner when there is no drift', () => {
    render(withQueryClient(<SpecPage />))
    expect(screen.queryByText(/drift item/)).not.toBeInTheDocument()
  })

  it('shows the drift banner with a count when the Hub reports drift', () => {
    specListResult.data.diagnostics = [
      { code: 'unfiled_document', path: 'spec/extra.html' },
      { code: 'stale_row', path: 'spec/old.html' },
    ]
    render(withQueryClient(<SpecPage />))
    expect(screen.getByText('2 spec manifest drift items')).toBeInTheDocument()
  })

  it('does not double-count missing documents reported in both diagnostics and missing', () => {
    specListResult.data.diagnostics = [
      { code: 'unfiled_document', path: 'spec/extra.html' },
      { code: 'missing_document', path: 'spec/changes/gone/spec.html' },
    ]
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html' }]
    render(withQueryClient(<SpecPage />))
    expect(screen.getByText('2 spec manifest drift items')).toBeInTheDocument()
    fireEvent.click(screen.getByText('2 spec manifest drift items'))
    // The missing path appears exactly once (from `missing`, not duplicated
    // by the `missing_document` diagnostic).
    expect(screen.getAllByText(/spec\/changes\/gone\/spec\.html/)).toHaveLength(1)
  })

  it('expands to list diagnostic details on click', () => {
    specListResult.data.diagnostics = [{ code: 'unfiled_document', path: 'spec/extra.html' }]
    render(withQueryClient(<SpecPage />))
    expect(screen.queryByText(/unfiled_document/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('1 spec manifest drift item'))
    expect(screen.getByText(/unfiled_document — spec\/extra\.html/)).toBeInTheDocument()
  })

  it('reports drift without offering to repair it', () => {
    specListResult.data.diagnostics = [{ code: 'stale_row', path: 'spec/old.html' }]
    render(withQueryClient(<SpecPage />))

    expect(screen.getByText('1 spec manifest drift item')).toBeInTheDocument()
    // The button instructed an uninstalled skill. A deterministic reindexer belongs in B2,
    // where the manifest format it repairs against will exist.
    expect(screen.queryByText('Repair manifest')).not.toBeInTheDocument()
  })

  it('prefers the manifest home over spec/spec.html for default selection', () => {
    specListResult.data.specs = [
      { path: 'spec/spec.html' },
      { path: 'spec/agentweave-spec.html', title: 'Baseline', kind: 'baseline', state: 'filed' },
    ]
    specListResult.data.home = 'spec/agentweave-spec.html'
    render(withQueryClient(<SpecPage />))
    // The flat path selector was replaced by the document library, so home
    // selection is now observed as the current row rather than a select value.
    // Scoped to the library because the iframe also titles itself with the path.
    const library = within(screen.getByTestId('spec-document-list'))
    expect(library.getByTitle('spec/agentweave-spec.html')).toHaveAttribute('aria-current', 'true')
  })
})
