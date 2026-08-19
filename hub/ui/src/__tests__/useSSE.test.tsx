import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, getBufferedEvents, __resetSSEStateForTest } from '@/hooks/useSSE'
import type { ReactNode } from 'react'

function makeSSEResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

describe('S3 — useSSE auth: Authorization header, no ?token= in URL', () => {
  let fetchSpy: ReturnType<typeof vi.fn>
  let eventSourceCtorCount: number

  beforeEach(() => {
    __resetSSEStateForTest()
    fetchSpy = vi.fn()
    eventSourceCtorCount = 0
    function FakeEventSource() {
      eventSourceCtorCount++
    }
    ;(FakeEventSource as unknown as Record<string, unknown>).prototype = {
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onerror: null,
      onmessage: null,
      onopen: null,
      readyState: 1,
    }
    // @ts-expect-error - intentional global stub
    globalThis.EventSource = FakeEventSource
    globalThis.fetch = fetchSpy as unknown as typeof fetch
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY123',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
    })
  })

  afterEach(() => {
    __resetSSEStateForTest()
  })

  it('calls fetch with the events URL and an Authorization header (no ?token=)', async () => {
    fetchSpy.mockResolvedValue(makeSSEResponse([]))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://hub.test/api/v1/events')
    expect(url).not.toContain('?token=')
    expect(url).not.toContain('aw_live_')
    const headers = (init.headers ?? {}) as Record<string, string>
    expect(headers.Authorization).toBe('Bearer aw_live_TESTKEY123')
  })

  it('does not construct a raw EventSource (the legacy leak vector)', async () => {
    fetchSpy.mockResolvedValue(makeSSEResponse([]))

    function Probe() {
      useSSE()
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    expect(eventSourceCtorCount).toBe(0)
  })

  it('dispatches a named SSE event to the buffer and listeners when a chunk arrives', async () => {
    const payload = JSON.stringify({ id: 'msg-1', subject: 'hi' })
    fetchSpy.mockResolvedValue(
      makeSSEResponse([`event: message_created\ndata: ${payload}\n\n`])
    )

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toContain('message_created'))
    const buffered = getBufferedEvents()
    expect(buffered.some((b) => b.type === 'message_created')).toBe(true)
  })

  it('dispatches session_synced (broadcast by the CLI-roster sync endpoint, consumed by useAgents)', async () => {
    const payload = JSON.stringify({ agents: ['alice'] })
    fetchSpy.mockResolvedValue(
      makeSSEResponse([`event: session_synced\ndata: ${payload}\n\n`])
    )

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toContain('session_synced'))
  })

  it('dispatches job_created/job_updated/job_deleted/job_fired (broadcast by jobs.py and scheduler.py, previously dropped)', async () => {
    const frames = ['job_created', 'job_updated', 'job_deleted', 'job_fired']
      .map((type) => `event: ${type}\ndata: {"id":"job-1"}\n\n`)
      .join('')
    fetchSpy.mockResolvedValue(makeSSEResponse([frames]))

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() =>
      expect(seen).toEqual(expect.arrayContaining(['job_created', 'job_updated', 'job_deleted', 'job_fired']))
    )
  })

  it('dispatches run_started/run_completed/run_failed/run_stopped/run_interrupted (broadcast by agent_trigger.py/run_reconciliation.py, tasks 3.6/3.7/3.8)', async () => {
    const types = ['run_started', 'run_completed', 'run_failed', 'run_stopped', 'run_interrupted']
    const frames = types
      .map((type) => `event: ${type}\ndata: {"agent":"claude","run_id":"run-1"}\n\n`)
      .join('')
    fetchSpy.mockResolvedValue(makeSSEResponse([frames]))

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toEqual(expect.arrayContaining(types)))
  })

  it(
    'dispatches loop_stopped/loop_queue_exhausted/loop_archived/loop_control_changed/' +
      'loop_edit_staged/loop_edit_applied (task B6.4, 2026-08-18-a-loop-writes-its-own-queue — ' +
      'previously dropped, since none were in SSE_EVENT_TYPES)',
    async () => {
      const types = [
        'loop_stopped',
        'loop_queue_exhausted',
        'loop_archived',
        'loop_control_changed',
        'loop_edit_staged',
        'loop_edit_applied',
      ]
      const frames = types
        .map((type) => `event: ${type}\ndata: {"loop_id":"loop-1"}\n\n`)
        .join('')
      fetchSpy.mockResolvedValue(makeSSEResponse([frames]))

      const seen: string[] = []
      function Probe() {
        useSSE((e) => {
          seen.push(e.type)
        })
        return null
      }
      render(withQueryClient(<Probe />))

      await waitFor(() => expect(seen).toEqual(expect.arrayContaining(types)))
    }
  )

  it('invalidates the loops list and this loop_id on each of the six loop_* events, and on job_fired/a terminal run event', async () => {
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries')

    const frames = [
      'event: loop_queue_exhausted\ndata: {"project_id":"proj-1","loop_id":"loop-1"}\n\n',
      'event: loop_archived\ndata: {"project_id":"proj-1","id":"loop-2"}\n\n',
      'event: job_fired\ndata: {"project_id":"proj-1","id":"job-1"}\n\n',
      'event: run_completed\ndata: {"project_id":"proj-1","agent":"claude","run_id":"run-1"}\n\n',
    ].join('')
    fetchSpy.mockResolvedValue(makeSSEResponse([frames]))

    function Probe() {
      useSSE()
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>
    )

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'proj-1', 'loops', 'loop-1'] })
    )
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'proj-1', 'loops', 'loop-2'] })
    // job_fired and a terminal run event invalidate the list even with no loop id in their own
    // payload — a firing's own job/run events don't name the loop, only the job/run.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['project', 'proj-1', 'loops'] })
  })

  it('dispatches permission_denied, so a refused agent is visible rather than silent', async () => {
    // Not in SSE_EVENT_TYPES means dropped client-side before any handler runs, and the
    // operator never learns the agent hit a wall.
    fetchSpy.mockResolvedValue(
      makeSSEResponse([
        'event: permission_denied\ndata: {"agent":"walled","tool_name":"Write","reason":"outside your workspace"}\n\n',
      ])
    )

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toContain('permission_denied'))
  })

  it('dispatches inbound queue lifecycle events', async () => {
    const types = [
      'queue_entry_queued',
      'queue_entry_delivered',
      'queue_entry_withdrawn',
      'queue_chain_suspended',
    ]
    const frames = types
      .map((type) => `event: ${type}\ndata: {"agent":"claude","entry_id":"entry-1"}\n\n`)
      .join('')
    fetchSpy.mockResolvedValue(makeSSEResponse([frames]))

    const seen: string[] = []
    function Probe() {
      useSSE((e) => {
        seen.push(e.type)
      })
      return null
    }
    render(withQueryClient(<Probe />))

    await waitFor(() => expect(seen).toEqual(expect.arrayContaining(types)))
  })
})
