import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// A pre-review run starting, getting its slot, or ending refetches the task list and the build read,
// and so does a review run starting, which moves its task to In review, and a firing, which starts a
// task's run.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

describe('check events refetch the task list and the build read', () => {
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
    ['task_checks_started', { task_id: 't1', run_id: 'r1', slot: false }],
    ['task_checks_started', { task_id: 't1', run_id: 'r1', slot: true }],
    ['task_checks_finished', { task_id: 't1', state: 'failed' }],
    ['task_updated', { id: 't1', status: 'completed' }],
    ['run_started', { run_id: 'r2', agent: 'QA', task_id: 't1' }],
    ['job_fired', { id: 'job-1', agent: 'Dev', job_run_id: 'jr-1' }],
  ])('%s refetches both', async (type, data) => {
    let tasks = 0
    let read = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'tasks'], queryFn: async () => ++tasks, staleTime: Infinity })
      useQuery({ queryKey: ['project', 'p', 'builds', 'read', 'b1'], queryFn: async () => ++read, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(tasks + read).toBe(2))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame(type, data))
      await new Promise((r) => setTimeout(r, 250))
    })
    expect(tasks).toBeGreaterThanOrEqual(2)
    expect(read).toBeGreaterThanOrEqual(2)
  })
})

// A stage event that lands on a read in flight does not cancel it and send a second copy: the Hub
// still serves a cancelled request (`hub-responsiveness-under-agent-load`, no-duplicate-in-flight).
// The one follow-up goes out the moment the first answers, so the new stage is one read behind.
describe('a stage event on a read in flight gets one follow-up, after it answers', () => {
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
    ['task_updated', { id: 't1', status: 'completed' }, ['project', 'p', 'builds', 'read', 'b1']],
    ['task_updated', { id: 't1', status: 'completed' }, ['project', 'p', 'tasks']],
    ['task_checks_started', { task_id: 't1', run_id: 'r1', slot: false }, ['project', 'p', 'builds', 'read', 'b1']],
    ['task_checks_started', { task_id: 't1', run_id: 'r1', slot: false }, ['project', 'p', 'tasks']],
    ['task_checks_finished', { task_id: 't1', state: 'passed' }, ['project', 'p', 'builds', 'read', 'b1']],
    ['run_started', { run_id: 'r2', agent: 'QA', task_id: 't1' }, ['project', 'p', 'builds', 'read', 'b1']],
    ['job_fired', { id: 'job-1', agent: 'Dev' }, ['project', 'p', 'tasks']],
  ])('%s (%j) on %j', async (type, data, key) => {
    const answers: Array<(n: number) => void> = []
    let calls = 0
    let open = 0
    let mostOpen = 0
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useSSE()
      useQuery({
        queryKey: key,
        queryFn: () => {
          calls += 1
          if (calls === 1) return Promise.resolve(0)
          open += 1
          mostOpen = Math.max(mostOpen, open)
          return new Promise<number>((resolve) =>
            answers.push((n) => {
              open -= 1
              resolve(n)
            }),
          )
        },
        staleTime: Infinity,
      })
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(calls).toBe(1))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      // A poll goes out and has not answered when the events arrive.
      void client.refetchQueries({ queryKey: key })
      await new Promise((r) => setTimeout(r, 10))
    })
    expect(calls).toBe(2)
    await act(async () => {
      push(frame(type, data))
      push(frame(type, data))
      push(frame(type, data))
      await new Promise((r) => setTimeout(r, 100))
    })
    // Nothing more is sent while the first is unanswered.
    expect(calls).toBe(2)
    await act(async () => {
      answers[0](1)
      await new Promise((r) => setTimeout(r, 30))
    })
    // Its answer sends exactly one follow-up, at once.
    expect(calls).toBe(3)
    await act(async () => {
      answers[1](2)
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(calls).toBe(3)
    expect(mostOpen).toBe(1)
    expect(client.getQueryData(key)).toBe(2)
  })
})
