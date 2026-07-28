import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
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

// The spec document itself is irrelevant here — every assertion is about the
// trigger body and the new-session flag lifecycle.
vi.mock('@/api/spec', () => ({
  useSpecList: () => ({
    data: { specs: [{ path: 'spec/spec.html' }] },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: { path: 'spec/spec.html', content: '<html></html>' }, refetch: () => {} }),
  useSpecEvents: () => {},
}))

// Controlled by each test.
let sessionsResult: { sessions: { id: string }[] } = { sessions: [{ id: 'ses_prior' }] }
let agentStatus = 'idle'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      {
        name: 'spec',
        status: agentStatus,
        message_count: 0,
        active_task_count: 0,
        dev_roles: ['spec'],
      },
      { name: 'other', status: 'idle', message_count: 0, active_task_count: 0 },
    ],
  }),
  useAgentOutput: () => ({ lines: [], isLoading: false }),
  useAgentSessions: () => ({ data: sessionsResult }),
}))

const fetchWithAuth = vi.fn()
vi.mock('@/api/client', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuth(...args),
}))

import { SpecPage } from '@/components/spec/SpecPage'

// One client per test, so a rerender does not swap the query context out.
let queryClient: QueryClient

function withQueryClient(node: ReactNode) {
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
}

/** Parse the JSON body of the Nth /agent/trigger call. */
function triggerBody(call = 0): Record<string, unknown> {
  const [path, init] = fetchWithAuth.mock.calls[call] as [string, RequestInit]
  expect(path).toBe('/api/v1/agent/trigger')
  return JSON.parse(init.body as string)
}

async function sendMessage(text: string) {
  const textarea = screen.getByPlaceholderText(/^Message /)
  fireEvent.change(textarea, { target: { value: text } })
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
  await waitFor(() => expect(fetchWithAuth).toHaveBeenCalled())
}

describe('Spec tab chat — session resume', () => {
  beforeEach(() => {
    cleanup()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    fetchWithAuth.mockReset()
    fetchWithAuth.mockResolvedValue({ ok: true, status: 200 })
    sessionsResult = { sessions: [{ id: 'ses_prior' }] }
    agentStatus = 'idle'
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

  it('sends session_mode "resume" with no session_id', async () => {
    render(withQueryClient(<SpecPage />))
    await sendMessage('hello')

    const body = triggerBody()
    expect(body.session_mode).toBe('resume')
    expect(body.session_id).toBeUndefined()
    expect(body.agent).toBe('spec')
  })

  it('sends session_mode "new" when the new-session control is armed', async () => {
    render(withQueryClient(<SpecPage />))
    fireEvent.click(screen.getByLabelText('Start a new session'))
    await sendMessage('fresh start')

    expect(triggerBody().session_mode).toBe('new')
  })

  it('clears the flag after one message, so the next message resumes', async () => {
    const { rerender } = render(withQueryClient(<SpecPage />))
    fireEvent.click(screen.getByLabelText('Start a new session'))
    await sendMessage('fresh start')
    expect(triggerBody(0).session_mode).toBe('new')

    await waitFor(() =>
      expect(screen.getByLabelText('Start a new session')).toHaveAttribute('aria-pressed', 'false')
    )

    // The input stays disabled until the agent has run and gone idle again.
    // Drive that queued -> running -> idle cycle so a second send is possible.
    agentStatus = 'running'
    rerender(withQueryClient(<SpecPage />))
    agentStatus = 'idle'
    rerender(withQueryClient(<SpecPage />))
    await waitFor(() => expect(screen.getByPlaceholderText(/^Message /)).not.toBeDisabled())

    await sendMessage('follow up')
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledTimes(2))
    expect(triggerBody(1).session_mode).toBe('resume')
  })

  it('clears the flag when the selected agent changes', async () => {
    render(withQueryClient(<SpecPage />))
    const newSessionBtn = screen.getByLabelText('Start a new session')
    fireEvent.click(newSessionBtn)
    expect(newSessionBtn).toHaveAttribute('aria-pressed', 'true')

    fireEvent.change(screen.getByDisplayValue('spec'), { target: { value: 'other' } })
    await waitFor(() =>
      expect(screen.getByLabelText('Start a new session')).toHaveAttribute('aria-pressed', 'false')
    )

    await sendMessage('hi other')
    expect(triggerBody().session_mode).toBe('resume')
    expect(triggerBody().agent).toBe('other')
  })

  describe('continuity indicator', () => {
    it('says the conversation continues when the agent has a saved session', () => {
      render(withQueryClient(<SpecPage />))
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        "Continuing spec's most recent session"
      )
    })

    it('says the next message starts one when there is no saved session', () => {
      sessionsResult = { sessions: [] }
      render(withQueryClient(<SpecPage />))
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'No session yet — the next message starts one'
      )
    })

    it('reflects the pending new-session state', () => {
      render(withQueryClient(<SpecPage />))
      fireEvent.click(screen.getByLabelText('Start a new session'))
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'Next message starts a new session'
      )
    })
  })
})
