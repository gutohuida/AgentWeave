import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest, refreshProjectsSoon, PROJECTS_REFRESH_MS } from '@/hooks/useSSE'

// The project collection is read over every registered project. Refetched by each page on every
// run event and heartbeat, it was in flight on all three of the drive's pages for most of a build,
// and the task lists and build read the same events asked for answered seconds apart (drive run
// 174800: the map said Building for 3.4 s after the board said Pre-review checks). The stage reads
// go at once; the project collection follows a few seconds later, once per burst (TSBVD-11).
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

describe('run events and heartbeats read the stage first and the project collection after', () => {
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

  it.each([
    ['run_started', { agent: 'Developer', run_id: 'run-1' }],
    ['run_completed', { agent: 'Developer', run_id: 'run-1' }],
    ['agent_heartbeat', { agent: 'Developer' }],
  ])('%s refetches the task list at once and the project collection once, seconds later', async (type, data) => {
    let tasks = 0
    let projects = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'tasks'], queryFn: async () => ++tasks, staleTime: Infinity })
      useQuery({ queryKey: ['projects'], queryFn: async () => ++projects, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(tasks + projects).toBe(2))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame(type, data))
      push(frame(type, data))
      push(frame(type, data))
      await new Promise((r) => setTimeout(r, 250))
    })
    expect(tasks).toBeGreaterThanOrEqual(2)
    expect(projects).toBe(1)
    await waitFor(() => expect(projects).toBe(2), { timeout: PROJECTS_REFRESH_MS + 1500 })
    await new Promise((r) => setTimeout(r, 300))
    expect(projects).toBe(2)
  }, PROJECTS_REFRESH_MS * 3)
})

describe('refreshProjectsSoon', () => {
  afterEach(() => vi.useRealTimers())

  it('waits while a read of the collection is still being answered', () => {
    vi.useFakeTimers()
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries').mockResolvedValue(undefined)
    client.getQueryCache().build(client, { queryKey: ['projects'] }).setState({ fetchStatus: 'fetching' })
    for (let i = 0; i < 10; i++) refreshProjectsSoon(client)
    vi.advanceTimersByTime(PROJECTS_REFRESH_MS * 2)
    expect(spy).not.toHaveBeenCalled()
    client.getQueryCache().find({ queryKey: ['projects'] })!.setState({ fetchStatus: 'idle' })
    vi.advanceTimersByTime(PROJECTS_REFRESH_MS)
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenCalledWith({ queryKey: ['projects'] })
  })
})
