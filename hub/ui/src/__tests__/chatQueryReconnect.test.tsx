import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAgentChatHistory } from '@/api/agentChat'
import { cancelReconnect, useSSE, __resetSSEStateForTest } from '@/hooks/useSSE'
import { useConfigStore } from '@/store/configStore'

/**
 * F274, task 4.9 — a reconnect refetches the chat query.
 *
 * This pins EXISTING behaviour rather than new code, and it is that requirement's only guard.
 * The map of run facts moved onto the chat response, and one case it has to cover has no event
 * of its own: `reconcile_interrupted_runs()` is awaited inside the lifespan (`main.py:402`,
 * before `yield`), so its `run_interrupted` broadcast happens before uvicorn serves anything and
 * no reconnecting client can be subscribed yet. What covers that case is `useSSE`'s reconnect
 * handler, which invalidates EVERY query (`useSSE.ts:404-412`) — nothing else fails if that is
 * narrowed to a filtered call.
 *
 * Driven through `useSSE`'s own reconnect path, not through a per-hook mock: the layer under
 * test is the one `agentOutput-polling.test.tsx` mocks, so that shape would assert nothing here.
 * `useSSE-lifecycle.test.tsx` already spies `invalidateQueries` — but a spy passes for a filtered
 * call too, which is exactly the mutation this has to kill, so this one counts real refetches of
 * a real chat query instead.
 */

const CHAT_URL = 'http://hub.test/api/v1/projects/proj-test/agent/claude/chat/conv-1'

function Probe() {
  useSSE()
  useAgentChatHistory('claude', 'conv-1')
  return null
}

/** A stream that yields one keepalive then closes on its own — the "ended unexpectedly" path
 *  `useSSE-lifecycle.test.tsx` uses, which schedules a real 3000 ms reconnect. */
function closingEventStream(): Response {
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
}

describe('an SSE reconnect refetches the chat query the run facts ride on', () => {
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
    vi.restoreAllMocks()
  })

  it(
    'fetches the chat history a second time once the stream actually reconnects',
    async () => {
      let streamConnects = 0
      let chatFetches = 0
      ;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi
        .fn()
        .mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input)
          if (url.endsWith('/api/v1/events')) {
            streamConnects += 1
            return closingEventStream()
          }
          if (url === CHAT_URL) {
            chatFetches += 1
            return new Response(
              JSON.stringify({
                conversation_id: 'conv-1',
                session_id: null,
                agent: 'claude',
                entries: [],
                runs: {},
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            )
          }
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        })

      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      render(
        <QueryClientProvider client={client}>
          <Probe />
        </QueryClientProvider>,
      )

      // The initial connect is not a reconnect and must not invalidate anything, so the chat
      // query is fetched exactly once by its own mount.
      await waitFor(() => expect(streamConnects).toBe(1))
      await waitFor(() => expect(chatFetches).toBe(1))

      // The stream closing on its own schedules the 3000 ms reconnect; the second connect is
      // the real one, and the invalidation that follows it is what this test exists for.
      await waitFor(() => expect(streamConnects).toBe(2), { timeout: 6000 })
      await waitFor(() => expect(chatFetches).toBeGreaterThan(1), { timeout: 6000 })
    },
    12000,
  )
})
