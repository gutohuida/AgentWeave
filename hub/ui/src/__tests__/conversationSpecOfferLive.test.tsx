import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, __resetSSEStateForTest } from '@/hooks/useSSE'
import { ConversationSpecOffers } from '@/components/conversation/ConversationSpecOffers'
import { useConversationSpecDocuments } from '@/api/conversationSpec'

/** `every-spec-entry-point-leads-into-the-journey`, FR-7: a conversation already open when its agent
 *  creates a change document shows the notice without being remounted. The Hub announces the
 *  create (and the run's end) as `spec_updated`. */

const NEW = { path: 'spec/changes/new/spec.json', title: 'A new change', step: 'intake', created_by: 'claude', created_at: null }

let hubOffers: unknown[]
let push: (frame: string) => void

function Open() {
  useSSE()
  const read = useConversationSpecDocuments('proj-1', 'conv-1')
  return <ConversationSpecOffers offers={read.data?.offers ?? []} onAnswer={() => {}} />
}

beforeEach(() => {
  __resetSSEStateForTest()
  hubOffers = []
  const encoder = new TextEncoder()
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/api/v1/events')) {
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            push = (frame) => controller.enqueue(encoder.encode(frame))
          },
        })
        return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
      }
      const body = url.endsWith('/spec-documents') ? { attached: null, offers: hubOffers } : {}
      return { ok: true, status: 200, json: async () => body } as unknown as Response
    }),
  )
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-1',
    isConfigured: true,
  })
})

afterEach(() => {
  __resetSSEStateForTest()
  vi.unstubAllGlobals()
})

describe('the notice in a conversation that is already open', () => {
  it.each([
    ['the document is created', { path: NEW.path, phase: 'exploring', project_id: 'proj-1' }],
    ['the turn ends', { run_ended: 'run-1', project_id: 'proj-1' }],
  ])('appears when %s', async (_name, data) => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Open />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(push).toBeDefined())
    expect(screen.queryByTestId('conversation-spec-offer')).toBeNull()

    hubOffers = [NEW]
    push(`event: spec_updated\ndata: ${JSON.stringify(data)}\n\n`)

    const offer = await screen.findByTestId('conversation-spec-offer')
    expect(offer.getAttribute('data-path')).toBe(NEW.path)
  })
})
