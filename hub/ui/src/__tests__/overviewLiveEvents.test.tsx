import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest, type SSEEvent } from '@/hooks/useSSE'

/** Design D10: the one Overview read is refetched by the events that move what it shows, and by the
 *  note's own three; an output line moves nothing on it. Driven through the real stream. */

const EVENTS: [string, Record<string, unknown>][] = [
  ['stall_recorded', { id: 's1' }],
  ['known_failing_changed', {}],
  ['overview_note_started', { trigger: 'visit' }],
  ['overview_note_written', { note_id: 'n1' }],
  ['overview_note_failed', { reason: 'no runner' }],
  ['agent_output', { agent: 'Developer', line: 'x' }],
]

describe('the Overview follows the stream', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'p', isConfigured: true, bootstrapState: 'ready' })
  })
  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it.each(EVENTS)('%s', async (type, data) => {
    ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi.fn().mockImplementation(async () => {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode(`event: ${type}\ndata: ${JSON.stringify({ ...data, project_id: 'p' })}\n\n`))
        },
      })
      return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(client, 'invalidateQueries')
    const seen: SSEEvent[] = []
    function Probe() {
      useSSE((event) => {
        seen.push(event)
      })
      return null
    }
    const { unmount } = render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(seen.some((e) => e.type === type)).toBe(true))
    const keys = spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey?: unknown[] } | undefined)?.queryKey))
    if (type === 'agent_output') expect(keys).not.toContain(JSON.stringify(['project', 'p', 'overview']))
    else expect(keys).toContain(JSON.stringify(['project', 'p', 'overview']))
    unmount()
  })
})
