import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest, type SSEEvent } from '@/hooks/useSSE'

// F1039: the last subscriber unmounting while the stream's fetch was still in flight (StrictMode's
// mount, unmount, mount does exactly this) let the remount start a second fetch, and both streams
// then stayed open: every event reached every listener twice (the notifier counted one question as
// two). A stale attempt must close its own stream when it resolves.
describe('F1039 — one stream, even when the subscriber remounts while connecting', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('delivers each event once', async () => {
    const open: boolean[] = []
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi.fn().mockImplementation(async () => {
      const index = open.push(true) - 1
      // The Hub answers after the remount has happened, as a real request does.
      await new Promise((resolve) => setTimeout(resolve, 10))
      // The stale attempt's stream is cancelled before its event is due; a real server stops
      // writing to a closed connection, so the pending write is dropped rather than thrown.
      let pending: ReturnType<typeof setTimeout> | undefined
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          pending = setTimeout(() => {
            controller.enqueue(new TextEncoder().encode(
              'event: question_asked\ndata: {"id":"q-1","from_agent":"Developer","blocking":false,"project_id":"p"}\n\n',
            ))
          }, 30)
        },
        cancel() {
          clearTimeout(pending)
          open[index] = false
        },
      })
      return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    })

    const seen: SSEEvent[] = []
    function Probe() {
      useSSE((event) => {
        if (event.type === 'question_asked') seen.push(event)
      })
      return null
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { unmount } = render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <Probe />
        </QueryClientProvider>
      </StrictMode>,
    )
    await waitFor(() => expect(seen.length).toBeGreaterThan(0))
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(seen).toHaveLength(1)
    expect(open.filter(Boolean)).toHaveLength(1)
    unmount()
  })
})
