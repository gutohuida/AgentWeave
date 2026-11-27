import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// TSBVD-11, drive run 184251: the board and the map read a task's stage from the task list, the
// build view from the build read, and on a busy Hub the two answered one event up to two seconds
// apart. A `task_stage` frame carries the stage itself and reaches every page at once; each page
// puts it into every read that shows the task, and a read sent before it cannot undo it.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

const building = { stage: 'working', stage_since: '2026-11-26T18:58:00Z', check_state: null }
const checks = {
  stage: 'pre_review_checks',
  stage_since: '2026-11-26T18:59:00Z',
  stage_detail: null,
  stage_waits_on: null,
  check_state: { kind: 'pre_review', state: 'running' },
}

type Row = { id: string; title?: string; stage?: string | null; stage_since?: string | null; check_state?: unknown }

function deferred<T>() {
  let resolve: (value: T) => void = () => {}
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

describe('a task_stage frame moves every read that shows the task, at once', () => {
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

  it('patches the task list, the board, its prerequisite refs and the build read, refetching none', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const calls = { list: 0, board: 0, read: 0 }
    function Probe() {
      useSSE()
      useQuery({
        queryKey: ['project', 'p', 'tasks', {}],
        queryFn: async () => (++calls.list, { tasks: [{ id: 't1', title: 'Add hello.txt', ...building }], total: 1, has_more: false }),
        staleTime: Infinity,
      })
      useQuery({
        queryKey: ['project', 'p', 'tasks', 'board', 'doc'],
        queryFn: async () => (
          ++calls.board,
          {
            tasks: [
              { id: 't1', ...building },
              { id: 't2', ...building, prerequisites: [{ id: 't1', title: 'Add hello.txt', status: 'in_progress', ...building }] },
            ],
            edges: [],
          }
        ),
        staleTime: Infinity,
      })
      useQuery({
        queryKey: ['project', 'p', 'builds', 'read', 'b1'],
        queryFn: async () => (++calls.read, { build: { id: 'b1', state: 'running' }, tasks: [{ id: 't1', stage: 'working', check_state: null }] }),
        staleTime: Infinity,
      })
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(calls.list + calls.board + calls.read).toBe(3))
    const t2Before = (client.getQueryData(['project', 'p', 'tasks', 'board', 'doc']) as { tasks: Row[] }).tasks[1]
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('task_stage', { tasks: [{ id: 't1', ...checks }] }))
      await new Promise((r) => setTimeout(r, 80))
    })

    const list = client.getQueryData(['project', 'p', 'tasks', {}]) as { tasks: Row[] }
    const board = client.getQueryData(['project', 'p', 'tasks', 'board', 'doc']) as { tasks: Array<Row & { prerequisites?: Row[] }> }
    const read = client.getQueryData(['project', 'p', 'builds', 'read', 'b1']) as { tasks: Row[] }
    expect(list.tasks[0]).toMatchObject({ title: 'Add hello.txt', stage: 'pre_review_checks', stage_since: '2026-11-26T18:59:00Z', check_state: checks.check_state })
    expect(board.tasks[0].stage).toBe('pre_review_checks')
    expect(board.tasks[1].prerequisites?.[0].stage).toBe('pre_review_checks')
    expect(board.tasks[1].stage).toBe('working')
    expect(read.tasks[0]).toEqual({ id: 't1', stage: 'pre_review_checks', check_state: checks.check_state })
    expect(Object.keys(read.tasks[0])).not.toContain('stage_since')
    expect(calls).toEqual({ list: 1, board: 1, read: 1 })
    expect(board.tasks[1]).not.toBe(t2Before)
  })

  it('a read sent before the frame keeps the frame; a read sent after it is taken as it came', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    let answer: ReturnType<typeof deferred<{ tasks: Row[] }>> | null = null
    let reads = 0
    function Probe() {
      useSSE()
      useQuery({
        queryKey: ['project', 'p', 'builds', 'read', 'b1'],
        queryFn: () => {
          reads += 1
          if (reads === 1) return Promise.resolve<{ tasks: Row[] }>({ tasks: [{ id: 't1', stage: 'working', check_state: null }] })
          answer = deferred<{ tasks: Row[] }>()
          return answer.promise
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
    await waitFor(() => expect(reads).toBe(1))
    const stageNow = () => (client.getQueryData(['project', 'p', 'builds', 'read', 'b1']) as { tasks: Row[] }).tasks[0].stage

    // The read goes out, then the frame arrives, then the read answers with what it saw: older.
    await act(async () => {
      void client.invalidateQueries({ queryKey: ['project', 'p', 'builds', 'read', 'b1'] })
      await new Promise((r) => setTimeout(r, 30))
      push(frame('task_stage', { tasks: [{ id: 't1', ...checks }] }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(stageNow()).toBe('pre_review_checks')
    await act(async () => {
      answer?.resolve({ tasks: [{ id: 't1', stage: 'working', check_state: null }] })
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(stageNow()).toBe('pre_review_checks')

    // A read sent after the frame is the newer word, whatever it says.
    await act(async () => {
      void client.invalidateQueries({ queryKey: ['project', 'p', 'builds', 'read', 'b1'] })
      await new Promise((r) => setTimeout(r, 30))
      answer?.resolve({ tasks: [{ id: 't1', stage: 'waiting_for_review', check_state: null }] })
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(stageNow()).toBe('waiting_for_review')
  })

  it('a frame that changes nothing leaves every read as it was', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useSSE()
      useQuery({
        queryKey: ['project', 'p', 'tasks', {}],
        queryFn: async () => ({ tasks: [{ id: 't1', ...checks }], total: 1, has_more: false }),
        staleTime: Infinity,
      })
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(['project', 'p', 'tasks', {}])).toBeTruthy())
    const before = client.getQueryData(['project', 'p', 'tasks', {}])
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('task_stage', { tasks: [{ id: 't1', ...checks }, { id: 'elsewhere', ...building }] }))
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(client.getQueryData(['project', 'p', 'tasks', {}])).toBe(before)
  })
})
