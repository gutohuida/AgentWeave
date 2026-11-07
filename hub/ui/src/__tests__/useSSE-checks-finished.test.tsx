import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// A task's checks finishing refreshes the drawer's checks row; the PR notice has its own key.
const enc = new TextEncoder()
let push: (text: string) => void = () => {}

function frame(type: string, data: object): string {
  return `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`
}

describe('task_checks_finished and main_behind_github refresh what they should', () => {
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

  it('checks finishing refetches that task\'s checks, and main_behind_github refetches the notice', async () => {
    let checks = 0
    let notice = 0
    function Probe() {
      useSSE()
      useQuery({ queryKey: ['project', 'p', 'task', 't1', 'checks'], queryFn: async () => ++checks, staleTime: Infinity })
      useQuery({ queryKey: ['project', 'p', 'mainAgainstGitHub'], queryFn: async () => ++notice, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(checks + notice).toBe(2))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('task_checks_finished', { task_id: 't1', state: 'passed' }))
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(checks).toBe(2)
    expect(notice).toBe(1)
    await act(async () => {
      push(frame('main_behind_github', {}))
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(notice).toBe(2)
    expect(checks).toBe(2)
  })
})
