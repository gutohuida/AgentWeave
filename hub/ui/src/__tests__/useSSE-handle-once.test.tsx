import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// The dashboard handles each stream event once per tab, however many components subscribe, and a
// refresh asked for while the same request is in flight is coalesced into one follow-up.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

function installStream() {
  ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        push = (text) => controller.enqueue(enc.encode(text))
      },
    })
    return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
  })
}

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

describe('stream events are handled once per tab', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'p',
      isConfigured: true,
      bootstrapState: 'ready',
    })
    installStream()
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('one event with several subscribers gives one refresh', async () => {
    let fetches = 0
    const queryFn = vi.fn(async () => ++fetches)
    function Subscriber() {
      useSSE()
      return null
    }
    function Reader() {
      useQuery({ queryKey: ['project', 'p', 'agents'], queryFn, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={newClient()}>
        <Subscriber />
        <Subscriber />
        <Subscriber />
        <Subscriber />
        <Reader />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(fetches).toBe(1))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('context_warning', { agent: 'a' }))
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(fetches).toBe(2)
  })

  it('five rapid invalidations of an in-flight key give at most two fetches', async () => {
    let fetches = 0
    let concurrent = 0
    let peak = 0
    const queryFn = vi.fn(async () => {
      fetches += 1
      concurrent += 1
      peak = Math.max(peak, concurrent)
      await new Promise((r) => setTimeout(r, 60))
      concurrent -= 1
      return fetches
    })
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'agents'], queryFn, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={newClient()}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(fetches).toBe(1))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150))
    })
    const base = fetches
    await act(async () => {
      for (let i = 0; i < 5; i += 1) push(frame('context_warning', { agent: 'a' }))
      await new Promise((r) => setTimeout(r, 400))
    })
    expect(fetches - base).toBeGreaterThanOrEqual(1)
    expect(fetches - base).toBeLessThanOrEqual(2)
    expect(peak).toBe(1)
  })

  it('refreshing the agent list leaves an agent output seed alone', async () => {
    let list = 0
    let seed = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'agents'], queryFn: async () => ++list, staleTime: Infinity })
      useQuery({
        queryKey: ['project', 'p', 'agents', 'a', 'output', 'seed'],
        queryFn: async () => ++seed,
        staleTime: Infinity,
      })
      return null
    }
    render(
      <QueryClientProvider client={newClient()}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(list + seed).toBe(2))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('context_warning', { agent: 'a' }))
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(list).toBe(2)
    expect(seed).toBe(1)
  })
})
