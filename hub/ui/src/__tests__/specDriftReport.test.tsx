import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import type { AgentSummary } from '@/api/agents'

/* What used to be `specManifestRepair.test.tsx`.
 *
 * The "Repair manifest" button is gone (A1 task 3.5, design.md Decision 4): it composed
 * "Run aw-spec-reindex to repair spec/index.json" and sent it to an agent chosen by a hardcoded
 * name convention, through a second bespoke trigger path, instructing a skill nothing installs.
 * Its three tests went with it. Everything here is about the drift *report*, which stays —
 * showing a condition and offering to act on it are different things, and only the second one
 * was broken.
 *
 * The report moved with the document: it is part of the panel that opens beside a conversation,
 * not of a page that no longer exists.
 */

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

// The conversation is the whole agent surface, with its own suites. Stubbed here so these
// assertions stay about the drift report rather than about every api module it reads.
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: () => <div data-testid="conversation-surface" />,
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

// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => specListResult,
  useSpec: () => ({ data: { path: 'spec/spec.html', content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'spec', status: 'idle' }] }),
}))

import { ConversationView } from '@/components/agents/ConversationView'

let queryClient: QueryClient

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

function renderPanel(document: string | null = 'spec/spec.html') {
  return render(
    withQueryClient(
      <ConversationView
        agent={agent}
        conversationId="conv-1"
        document={document}
        onSelectConversation={() => {}}
        onOpenDocument={() => {}}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
      />,
    ),
  )
}

describe('the document panel — manifest drift report', () => {
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
    renderPanel()
    expect(screen.queryByText(/drift item/)).not.toBeInTheDocument()
  })

  it('shows the drift banner with a count when the Hub reports drift', () => {
    specListResult.data.diagnostics = [
      { code: 'unfiled_document', path: 'spec/extra.html' },
      { code: 'stale_row', path: 'spec/old.html' },
    ]
    renderPanel()
    expect(screen.getByText('2 spec manifest drift items')).toBeInTheDocument()
  })

  it('does not double-count missing documents reported in both diagnostics and missing', () => {
    specListResult.data.diagnostics = [
      { code: 'unfiled_document', path: 'spec/extra.html' },
      { code: 'missing_document', path: 'spec/changes/gone/spec.html' },
    ]
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html' }]
    renderPanel()
    expect(screen.getByText('2 spec manifest drift items')).toBeInTheDocument()
    fireEvent.click(screen.getByText('2 spec manifest drift items'))
    // The missing path appears exactly once (from `missing`, not duplicated by the
    // `missing_document` diagnostic).
    expect(screen.getAllByText(/spec\/changes\/gone\/spec\.html/)).toHaveLength(1)
  })

  it('expands to list diagnostic details on click', () => {
    specListResult.data.diagnostics = [{ code: 'unfiled_document', path: 'spec/extra.html' }]
    renderPanel()
    expect(screen.queryByText(/unfiled_document/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('1 spec manifest drift item'))
    expect(screen.getByText(/unfiled_document — spec\/extra\.html/)).toBeInTheDocument()
  })

  it('reports drift without offering to repair it', () => {
    specListResult.data.diagnostics = [{ code: 'stale_row', path: 'spec/old.html' }]
    renderPanel()

    expect(screen.getByText('1 spec manifest drift item')).toBeInTheDocument()
    // The button instructed an uninstalled skill. A deterministic reindexer belongs in B2,
    // where the manifest format it repairs against will exist.
    expect(screen.queryByText('Repair manifest')).not.toBeInTheDocument()
  })

  it('reports nothing at all when no document is open', () => {
    specListResult.data.diagnostics = [{ code: 'stale_row', path: 'spec/old.html' }]
    renderPanel(null)
    // Drift belongs to the document panel. With no document open the conversation is the whole
    // surface, and nothing specification-shaped is left on screen.
    expect(screen.queryByText(/drift item/)).not.toBeInTheDocument()
  })
})
