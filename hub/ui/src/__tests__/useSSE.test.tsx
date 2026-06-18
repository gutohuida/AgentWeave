import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, getBufferedEvents, __resetSSEStateForTest } from '@/hooks/useSSE'
import type { ReactNode } from 'react'

function makeSSEResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

describe('S3 — useSSE auth: Authorization header, no ?token= in URL', () => {
  let fetchSpy: ReturnType<typeof vi.fn>
  let eventSourceCtorCount: number

  beforeEach(() => {
    __resetSSEStateForTest()
    fetchSpy = vi.fn()
    eventSourceCtorCount = 0
    function FakeEventSource() {
      eventSourceCtorCount++
    }
    ;(FakeEventSource as unknown as Record<string, unknown>).prototype = {
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onerror: null,
      onmessage: null,
      onopen: null,
      readyState: 1,
    }
    // @ts-expect-error - intentional global stub
    globalThis.EventSource = FakeEventSource
    globalThis.fetch = fetchSpy as unknown as typeof fetch
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY123',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
    })
  })

  afterEach(() => {
    __resetSSEStateForTest()
  })

  it('calls fetch with the events URL and an Authorization header (no ?token=)', async () => {
    fetchSpy.mockResolvedValue(makeSSEResponse([]))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://hub.test/api/v1/events')
    expect(url).not.toContain('?token=')
    expect(url).not.toContain('aw_live_')
    const headers = (init.headers ?? {}) as Record<string, string>
    expect(headers.Authorization).toBe('Bearer aw_live_TESTKEY123')
  })

  it('does not construct a raw EventSource (the legacy leak vector)', async () => {
    fetchSpy.mockResolvedValue(makeSSEResponse([]))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    expect(eventSourceCtorCount).toBe(0)
  })

  it('dispatches a named SSE event to the buffer and listeners when a chunk arrives', async () => {
    const payload = JSON.stringify({ id: 'msg-1', subject: 'hi' })
    fetchSpy.mockResolvedValue(
      makeSSEResponse([`event: message_created\ndata: ${payload}\n\n`])
    )

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toContain('message_created'))
    const buffered = getBufferedEvents()
    expect(buffered.some((b) => b.type === 'message_created')).toBe(true)
  })
})
