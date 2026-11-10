import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'
import { noticeFrom } from '@/lib/notify/classify'

// The page's toasts are drawn from `operator_notice`; useSSE drops event types it does not list,
// so this pushes a real frame through the stream rather than calling noticeFrom directly.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

describe('operator_notice reaches the page listener', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'p',
      isConfigured: true,
      bootstrapState: 'ready',
    })
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async () => {
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          push = (text) => controller.enqueue(enc.encode(text))
        },
      })
      return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    })
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('delivers an operator_notice frame, which noticeFrom reads into a notice', async () => {
    const seen: Array<{ type: string; data: unknown }> = []
    function Probe() {
      useSSE((e) => seen.push({ type: e.type, data: e.data }))
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('operator_notice', { id: 'ntc-1', kind: 'ask', agent: 'Developer', conversation_id: 'conv-q', title: 'T', text: 'Developer asked you a question' }))
      await new Promise((r) => setTimeout(r, 150))
    })
    const got = seen.find((e) => e.type === 'operator_notice')
    expect(got).toBeTruthy()
    expect(noticeFrom(got!.type, got!.data)).toMatchObject({ kind: 'ask', projectId: 'p', conversationId: 'conv-q' })
  })
})
