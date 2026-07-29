import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
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

let agents: {
  name: string
  status: string
  message_count: number
  active_task_count: number
  dev_roles?: string[]
}[]

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: agents }),
  useAgentOutput: () => ({ lines: [], isLoading: false }),
  useAgentSessions: () => ({ data: { sessions: [] } }),
}))

const fetchWithAuth = vi.fn()
vi.mock('@/api/client', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args),
}))

import { SpecPage } from '@/components/spec/SpecPage'

let queryClient: QueryClient

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

function triggerBody(call = 0): Record<string, unknown> {
  const [path, init] = fetchWithAuth.mock.calls[call] as [string, RequestInit]
  expect(path).toBe('/api/v1/agent/trigger')
  return JSON.parse(init.body as string)
}

describe('Spec tab — manifest drift and repair', () => {
  beforeEach(() => {
    cleanup()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({ ok: true, status: 200 })
    agents = [
      { name: 'spec', status: 'idle', message_count: 0, active_task_count: 0, dev_roles: ['spec'] },
      { name: 'other', status: 'idle', message_count: 0, active_task_count: 0 },
    ]
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
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
      theme: 'cosmic',
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

  it('sends a bounded repair message to the idle spec-role agent', async () => {
    specListResult.data.diagnostics = [{ code: 'unfiled_document', path: 'spec/extra.html' }]
    specListResult.data.missing = [{ path: 'spec/changes/gone/spec.html' }]
    render(withQueryClient(<SpecPage />))

    fireEvent.click(screen.getByText('Repair manifest'))
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled())

    const body = triggerBody()
    expect(body.agent).toBe('spec')
    expect(body.session_mode).toBe('resume')
    const message = body.message as string
    expect(message).toContain('aw-spec-reindex')
    expect(message).toContain('unfiled_document')
    expect(message).toContain('spec/extra.html')
    expect(message).toContain('spec/changes/gone/spec.html')
  })

  it('falls back to the selected chat agent when no spec-role agent is idle', async () => {
    agents = [
      { name: 'spec', status: 'running', message_count: 0, active_task_count: 0, dev_roles: ['spec'] },
      { name: 'other', status: 'idle', message_count: 0, active_task_count: 0 },
    ]
    specListResult.data.diagnostics = [{ code: 'stale_row', path: 'spec/old.html' }]
    render(withQueryClient(<SpecPage />))

    // Default agent selection prefers the spec role even while busy, so pick
    // the fallback explicitly via the chat agent selector.
    fireEvent.change(screen.getByDisplayValue('spec'), { target: { value: 'other' } })

    await waitFor(() => expect(screen.getByText('Repair manifest')).not.toBeDisabled())
    fireEvent.click(screen.getByText('Repair manifest'))
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled())
    expect(triggerBody().agent).toBe('other')
  })

  it('disables the repair button when no eligible agent exists', () => {
    agents = [
      { name: 'spec', status: 'running', message_count: 0, active_task_count: 0, dev_roles: ['spec'] },
    ]
    specListResult.data.diagnostics = [{ code: 'stale_row', path: 'spec/old.html' }]
    render(withQueryClient(<SpecPage />))
    expect(screen.getByText('Repair manifest')).toBeDisabled()
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
