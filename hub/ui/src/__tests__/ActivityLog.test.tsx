import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import type { SSEEvent } from '@/hooks/useSSE'
import { getJson } from '@/api/client'

// Capture the callback that ActivityLog registers with useSSE. We mock the
// useSSE module so we can call the callback synchronously from the test —
// this isolates the stale-closure behavior of ActivityLog from the network.
const capturedCallback: { current: ((e: SSEEvent) => void) | null } = { current: null }

vi.mock('@/hooks/useSSE', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useSSE')>()
  return {
    ...actual,
    useSSE: (cb?: (e: SSEEvent) => void) => {
      capturedCallback.current = cb ?? null
    },
    getBufferedEvents: () => [],
    __resetSSEStateForTest: actual.__resetSSEStateForTest,
  }
})

// Mock the history fetch to return nothing — keeps the test focused on the
// SSE-paused behavior.
vi.mock('@/api/client', () => ({
  getJson: vi.fn().mockResolvedValue([]),
}))

// Mock eventSummary so the EventRow import doesn't choke on internals.
vi.mock('@/lib/eventSummary', () => ({
  summaryForEvent: () => 'mock',
}))

import { ActivityLog } from '@/components/activity/ActivityLog'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

// The operator stream stamps every event with project_id server-side
// (hub/hub/sse.py); ActivityLog filters on it to avoid blending projects.
function fakeEvent(type: string, data: Record<string, unknown> = {}): SSEEvent {
  return { type, data: { project_id: 'proj-test', ...data }, timestamp: new Date().toISOString() }
}

describe('M19 — ActivityLog uses a ref to read the latest paused value', () => {
  beforeEach(() => {
    capturedCallback.current = null
    vi.mocked(getJson).mockResolvedValue([])
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('registers an SSE callback on mount and adds events when not paused', async () => {
    render(withQueryClient(<ActivityLog />))
    await waitFor(() => expect(capturedCallback.current).not.toBeNull())

    act(() => {
      capturedCallback.current?.(fakeEvent('message_created', { id: 'm-1' }))
    })

    // The first event row should be present in the rendered output.
    expect(screen.getByText('message_created')).toBeInTheDocument()
  })

  it('after clicking Pause, the registered callback does NOT add events (no stale closure)', async () => {
    render(withQueryClient(<ActivityLog />))
    await waitFor(() => expect(capturedCallback.current).not.toBeNull())

    // Confirm the event is added when not paused.
    act(() => {
      capturedCallback.current?.(fakeEvent('message_created', { id: 'm-pre' }))
    })
    expect(screen.getAllByText('message_created').length).toBe(1)

    // Toggle Pause.
    fireEvent.click(screen.getByRole('button', { name: /pause/i }))

    // After clicking Pause, the SAME registered callback should drop events.
    act(() => {
      capturedCallback.current?.(fakeEvent('message_created', { id: 'm-post' }))
    })
    // Only the pre-pause event should be in the DOM.
    expect(screen.getAllByText('message_created').length).toBe(1)

    // Resume and verify events flow again.
    fireEvent.click(screen.getByRole('button', { name: /resume/i }))
    act(() => {
      capturedCallback.current?.(fakeEvent('message_created', { id: 'm-resume' }))
    })
    await waitFor(() =>
      expect(screen.getAllByText('message_created').length).toBeGreaterThanOrEqual(2)
    )
  })

  it('discards an old project history response after the selected project changes', async () => {
    const resolvers = new Map<string, (events: SSEEvent[]) => void>()
    vi.mocked(getJson).mockImplementation((url) => new Promise((resolve) => {
      resolvers.set(url, resolve as (events: SSEEvent[]) => void)
    }))
    render(withQueryClient(<ActivityLog />))
    await waitFor(() => expect(resolvers.has('/api/v1/projects/proj-test/events/history?limit=200')).toBe(true))

    act(() => useConfigStore.setState({ selectedProjectId: 'proj-next' }))
    await waitFor(() => expect(resolvers.has('/api/v1/projects/proj-next/events/history?limit=200')).toBe(true))

    await act(async () => {
      resolvers.get('/api/v1/projects/proj-test/events/history?limit=200')?.([
        { type: 'stale_project_event', data: { project_id: 'proj-test' }, timestamp: new Date().toISOString() },
      ])
      resolvers.get('/api/v1/projects/proj-next/events/history?limit=200')?.([])
      await Promise.resolve()
    })
    expect(screen.queryByText('stale_project_event')).not.toBeInTheDocument()
  })
})
