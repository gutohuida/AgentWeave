import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// The UI has no node typings: read the file the way node does.
// @ts-expect-error no node typings in the UI project
const { readFileSync } = (await import('node:fs')) as { readFileSync: (p: string, enc: string) => string }

// A task's checkout starting and finishing being prepared moves its stage into and out of
// "Preparing checkout": the board and the map (the task lists) and the build view (the build read)
// all refetch, so none of them shows "Not started" while another shows "Preparing checkout"
// (TSBVD-10; the drive saw both events dropped before they reached the handler).
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

describe('checkout preparation refetches the task lists and the build read', () => {
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

  // The payload `workspace_preparation.Preparation.payload()` sends, plus `ok` on the second.
  const payload = { id: 'prep-1', agent: 'Developer', task_id: 't1', conversation_id: 'c1', started_at: '2026-11-26T14:00:00+00:00' }

  it.each([
    ['workspace_preparing', payload],
    ['workspace_prepared', { ...payload, ok: true }],
  ])('%s refetches the board, the map and the build view', async (type, data) => {
    let tasks = 0
    let board = 0
    let read = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'tasks', { excludeArchivedCompleted: false }], queryFn: async () => ++tasks, staleTime: Infinity })
      useQuery({ queryKey: ['project', 'p', 'tasks', 'boards'], queryFn: async () => ++board, staleTime: Infinity })
      useQuery({ queryKey: ['project', 'p', 'builds', 'read', 'b1'], queryFn: async () => ++read, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(tasks + board + read).toBe(3))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame(type, data))
      await new Promise((r) => setTimeout(r, 250))
    })
    expect(tasks).toBeGreaterThanOrEqual(2)
    expect(board).toBeGreaterThanOrEqual(2)
    expect(read).toBeGreaterThanOrEqual(2)
  })

  it('a preparation with no task refetches no task list', async () => {
    let tasks = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'tasks'], queryFn: async () => ++tasks, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(tasks).toBe(1))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('workspace_preparing', { ...payload, task_id: null }))
      await new Promise((r) => setTimeout(r, 250))
    })
    expect(tasks).toBe(1)
  })
})

describe('every event the handler acts on is let through the stream', () => {
  it('each `case` in useSSE.ts names an entry of SSE_EVENT_TYPES', () => {
    const source = readFileSync('src/hooks/useSSE.ts', 'utf8')
    const start = source.indexOf('const SSE_EVENT_TYPES = [')
    const list = source.slice(start, source.indexOf(']', start))
    const known = new Set([...list.matchAll(/^\s*'([a-z_]+)',/gm)].map((m) => m[1]))
    const handled = new Set([...source.matchAll(/case '([a-z_]+)':/g)].map((m) => m[1]))
    expect(known.size).toBeGreaterThan(20)
    expect([...handled].filter((type) => !known.has(type))).toEqual([])
  })
})
