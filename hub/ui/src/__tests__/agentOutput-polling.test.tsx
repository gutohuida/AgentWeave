import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useAgentOutput } from '@/api/agents'
import type { SSEEvent } from '@/hooks/useSSE'

// Capture the callback that useAgentOutput registers with useSSE. The agents
// module calls `useSSE((event) => ...)` and we want to drive events from the
// test to verify the new gap-only polling behavior.
const capturedCallback: { current: ((e: SSEEvent) => void) | null } = { current: null }
const reconnectFired: { count: number } = { count: 0 }

vi.mock('@/hooks/useSSE', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useSSE')>()
  return {
    ...actual,
    useSSE: (cb?: (e: SSEEvent) => void) => {
      capturedCallback.current = cb ?? null
    },
    onSseReconnect: (cb: () => void) => {
      const wrapped = () => {
        reconnectFired.count += 1
        cb()
      }
      reconnectListeners.add(wrapped)
      return () => {
        reconnectListeners.delete(wrapped)
      }
    },
    getBufferedEvents: () => [],
    __resetSSEStateForTest: () => {
      actual.__resetSSEStateForTest()
      reconnectListeners.clear()
      reconnectFired.count = 0
    },
  }
})

// Module-level reconnection listener registry, mirroring the real useSSE.ts
// implementation. We expose a trigger from the test via `triggerReconnect()`.
const reconnectListeners = new Set<() => void>()
function triggerReconnect() {
  for (const cb of reconnectListeners) cb()
}

// Mock the client used by useAgentOutput's REST fetch and the polling fetch.
const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

// (helper removed — currently unused; see line-by-line assertions below)

describe('M21 — useAgentOutput polls only on detected SSE gaps, not on a 2s interval', () => {
  let setIntervalSpy: ReturnType<typeof vi.spyOn>
  let clearIntervalSpy: ReturnType<typeof vi.spyOn>

  beforeEach(async () => {
    const { __resetSSEStateForTest } = await import('@/hooks/useSSE')
    __resetSSEStateForTest()
    capturedCallback.current = null
    reconnectFired.count = 0
    fetchMock.mockReset()

    setIntervalSpy = vi.spyOn(globalThis, 'setInterval')
    clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')

    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  afterEach(() => {
    setIntervalSpy.mockRestore()
    clearIntervalSpy.mockRestore()
  })

  it('does NOT set up a recurring 2s polling interval (M21 RED → GREEN)', async () => {
    // The seed query returns empty; the initial poll will also fetch but find
    // nothing to merge. We don't care about the data here — only that the
    // hook does NOT call setInterval(..., 2000).
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    )

    function Probe() {
      useAgentOutput('claude')
      return null
    }
    render(withQueryClient(<Probe />))

    // Let the seed + initial poll finish.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    // Snapshot any setInterval calls at 2000 ms delay. The M21 fix replaces the
    // unconditional `setInterval(poll, 2000)` with a one-shot gap timer, so
    // this assertion must hold AFTER the fix. Before the fix, the original
    // code does call setInterval(poll, 2000) — the test would fail (RED).
    const callsAt2s = setIntervalSpy.mock.calls.filter((c: unknown[]) => c[1] === 2000)
    expect(callsAt2s).toEqual([])
  })

  it('still calls the initial poll on mount (seed-from-REST path)', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    )

    function Probe() {
      useAgentOutput('claude')
      return null
    }
    render(withQueryClient(<Probe />))

    // Wait for the seed query and the initial poll to run. The seed uses
    // getJson (not fetch), so the fetch call here is the initial poll.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const pollCalls = fetchMock.mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('/output')
    )
    expect(pollCalls.length).toBeGreaterThanOrEqual(1)
  })

  it('fires a poll when an SSE reconnect is observed', async () => {
    // The seed + initial poll: 2 fetches
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    )

    function Probe() {
      useAgentOutput('claude')
      return null
    }
    render(withQueryClient(<Probe />))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const beforeCount = fetchMock.mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('/output')
    ).length

    // Simulate an SSE reconnect: useSSE's onSseReconnect should fire the
    // hook's reconciler, which calls poll() once.
    act(() => {
      triggerReconnect()
    })

    await waitFor(() => {
      const afterCount = fetchMock.mock.calls.filter(
        (c) => typeof c[0] === 'string' && c[0].includes('/output')
      ).length
      expect(afterCount).toBe(beforeCount + 1)
    })
  })

  it('does not fire a poll when an SSE agent_output event arrives (SSE is the source)', async () => {
    // Seed + initial poll
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    )

    function Probe() {
      useAgentOutput('claude')
      return null
    }
    render(withQueryClient(<Probe />))
    await waitFor(() => expect(capturedCallback.current).not.toBeNull())

    const beforeCount = fetchMock.mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('/output')
    ).length

    // Simulate an SSE agent_output event for the same agent. The hook should
    // append the line to its cache and NOT fire a poll — SSE is the source
    // of truth here.
    act(() => {
      capturedCallback.current?.({
        type: 'agent_output',
        data: { id: 'l-1', agent: 'claude', content: 'hello', timestamp: '2026-01-01T00:00:00Z' },
        timestamp: '2026-01-01T00:00:00Z',
      })
    })

    // Give the test a tick — the hook should NOT have made a new poll.
    await new Promise((r) => setTimeout(r, 30))
    const afterCount = fetchMock.mock.calls.filter(
      (c) => typeof c[0] === 'string' && c[0].includes('/output')
    ).length
    expect(afterCount).toBe(beforeCount)
  })
})
