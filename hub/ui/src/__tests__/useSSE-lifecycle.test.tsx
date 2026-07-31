import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { useConfigStore } from '@/store/configStore'
import {
  useSSE,
  cancelReconnect,
  __resetSSEStateForTest,
  __setIdleTimeoutForTest,
  getSSEConnectionState,
  onSseStateChange,
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

  it('keeps the shared stream alive while another subscriber remains mounted', async () => {
    let streamCancelled = false
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(': keepalive\n\n'))
      },
      cancel() {
        streamCancelled = true
      },
    })
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
      .fn()
      .mockResolvedValue(new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }))

    function Probe() {
      useSSE()
      return null
    }
    const hideSecond: { current: ((hidden: boolean) => void) | null } = { current: null }
    function Pair() {
      const [showSecond, setShowSecond] = useState(true)
      hideSecond.current = (hidden) => setShowSecond(!hidden)
      return <><Probe />{showSecond && <Probe />}</>
    }

    const { unmount } = render(withQueryClient(<Pair />))
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1))

    // Removing one page must not cancel the global stream used by the other.
    act(() => hideSecond.current?.(true))
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(streamCancelled).toBe(false)

    unmount()
    await waitFor(() => expect(streamCancelled).toBe(true))
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

describe('stream-health: connection state and reconciliation on reconnect (task 2.4)', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('starts closed, moves to open once the stream connects, and to reconnecting when it ends unexpectedly', async () => {
    expect(getSSEConnectionState()).toBe('closed')

    const seen: string[] = []
    const unsubscribe = onSseStateChange((s) => seen.push(s))

    // A stream that yields one keepalive then closes on its own — the "ended
    // unexpectedly" path, not a deliberate unmount/cancel.
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(': keepalive\n\n'))
        controller.close()
      },
    })
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      )

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toContain('open'))
    await waitFor(() => expect(seen).toContain('reconnecting'))
    unsubscribe()
  })

  it(
    'invalidates all queries once the stream actually reconnects (not on the initial connect)',
    async () => {
      let callCount = 0
      ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
        .fn()
        .mockImplementation(async () => {
          callCount += 1
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(': keepalive\n\n'))
              controller.close()
            },
          })
          return new Response(stream, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        })

      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

      function Probe() {
        useSSE()
        return null
      }
      render(
        <QueryClientProvider client={client}>
          <Probe />
        </QueryClientProvider>
      )

      // First connect: not a reconnect, must not trigger the reconciliation invalidation.
      await waitFor(() => expect(callCount).toBe(1))
      expect(invalidateSpy).not.toHaveBeenCalled()

      // The stream closing on its own schedules a real reconnect (3000ms) —
      // wait for the second fetch, which is the actual reconnect.
      await waitFor(() => expect(callCount).toBe(2), { timeout: 5000 })
      expect(invalidateSpy).toHaveBeenCalled()
    },
    8000
  )

  it(
    'detects a silently-dead connection via the idle watchdog, not just read() rejecting or done:true',
    async () => {
      // Reproduces a real bug found by killing the live Hub process during
      // manual 2.5 verification: a stream whose peer dies without closing
      // the socket never rejects and never resolves done:true — reader.read()
      // just hangs forever, so without this watchdog the UI stayed on
      // "Live" indefinitely despite the server being gone.
      __setIdleTimeoutForTest(10)
      let cancelCalled = false
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          // One initial chunk so the reader loop begins, then nothing —
          // simulating the peer going silent without a FIN/RST.
          controller.enqueue(new TextEncoder().encode(': keepalive\n\n'))
        },
        cancel() {
          cancelCalled = true
        },
      })
      ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
        .fn()
        .mockResolvedValue(
          new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
        )

      function Probe() {
        useSSE()
        return null
      }
      render(withQueryClient(<Probe />))

      await waitFor(() => expect(getSSEConnectionState()).toBe('open'))
      // The idle-check interval itself still runs on the real 5s cadence;
      // the 10ms override just guarantees the very first tick trips it.
      await waitFor(() => expect(cancelCalled).toBe(true), { timeout: 7000 })
      await waitFor(() => expect(getSSEConnectionState()).toBe('reconnecting'))
    },
    8000
  )
})
