import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import {
  useSSE,
  cancelReconnect,
  __resetSSEStateForTest,
} from '@/hooks/useSSE'
import type { ReactNode } from 'react'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

type TimerArgs = [handler: () => void, delay?: number, ...rest: unknown[]]

function setTimeoutCallsOf(spy: ReturnType<typeof vi.spyOn>, delay: number): TimerArgs[] {
  return spy.mock.calls.filter((c: unknown[]) => c[1] === delay) as TimerArgs[]
}

describe('M22 — useSSE reconnect lifecycle: clear on cancel, clear on unmount', () => {
  let setTimeoutSpy: ReturnType<typeof vi.spyOn>
  let clearTimeoutSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    __resetSSEStateForTest()
    setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  afterEach(() => {
    setTimeoutSpy.mockRestore()
    clearTimeoutSpy.mockRestore()
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('exports cancelReconnect and it is callable without throwing', () => {
    expect(typeof cancelReconnect).toBe('function')
    expect(() => cancelReconnect()).not.toThrow()
  })

  it('schedules a reconnect timer when fetch fails, and cancelReconnect clears it', async () => {
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
      .fn()
      .mockRejectedValue(new Error('network down'))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => {
      const calls = setTimeoutCallsOf(setTimeoutSpy, 3000)
      expect(calls.length).toBeGreaterThan(0)
    })

    // Now cancel — clearTimeout should fire for that timer.
    clearTimeoutSpy.mockClear()
    cancelReconnect()
    expect(clearTimeoutSpy).toHaveBeenCalled()
  })

  it('does not schedule a new reconnect after the consumer unmounts', async () => {
    // Stream that never ends on its own — keeps the consumer "connected"
    // until unmount. We never close the controller manually; the unmount
    // path must be the one that aborts it.
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(': keepalive\n\n'))
      },
    })
    const response = new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
      .fn()
      .mockResolvedValue(response)

    function Probe() {
      useSSE()
      return null
    }
    const { unmount } = render(withQueryClient(<Probe />))
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())

    // Snapshot setTimeout calls; unmount; ensure no NEW 3000ms reconnect
    // is scheduled by the cleanup path.
    const beforeCount = setTimeoutCallsOf(setTimeoutSpy, 3000).length
    unmount()
    await new Promise((r) => setTimeout(r, 20))
    const afterCount = setTimeoutCallsOf(setTimeoutSpy, 3000).length
    expect(afterCount).toBe(beforeCount)
  })

  it('cancels the reconnect timer when clearConfig flips isConfigured to false', async () => {
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
      .fn()
      .mockRejectedValue(new Error('network down'))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    // Wait for the reconnect timer to be scheduled.
    await waitFor(() => {
      const calls = setTimeoutCallsOf(setTimeoutSpy, 3000)
      expect(calls.length).toBeGreaterThan(0)
    })

    // Simulate the user clicking "log out" / clearConfig.
    clearTimeoutSpy.mockClear()
    act(() => {
      useConfigStore.setState({ isConfigured: false, apiKey: '' })
    })

    // The useSSE hook must observe isConfigured = false and call clearTimeout
    // for the pending reconnect.
    await waitFor(() => expect(clearTimeoutSpy).toHaveBeenCalled())
  })
})
