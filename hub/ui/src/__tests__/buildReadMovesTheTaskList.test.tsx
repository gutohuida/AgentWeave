import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, cleanup, render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { buildReadKey, useBuildRead } from '@/api/buildRead'

// Drive run 132112: a landing moving from its checks to the merge announces nothing the board hears,
// and the build view found Landing on its own poll while the board and the map, which read the task
// list, still said Landing checks. A build read that moves a task's stage refetches the task list.

function read(stage: string, state: string) {
  return {
    build: { id: 'b1', state: 'running' },
    tasks: [{ id: 't1', stage, check_state: { kind: 'landing', state } }],
    build_runs: [],
    as_of: '2026-11-26T00:00:00Z',
  }
}

describe('a build read that moves a stage refetches the task list', () => {
  let answer = read('checking', 'running')

  beforeEach(() => {
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'p',
      isConfigured: true,
      bootstrapState: 'ready',
    })
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
  })

  afterEach(cleanup)

  async function mount() {
    let tasks = 0
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Probe() {
      useBuildRead('b1')
      useQuery({ queryKey: ['project', 'p', 'tasks', {}], queryFn: async () => ++tasks, staleTime: Infinity })
      return null
    }
    render(
      <QueryClientProvider client={client}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(buildReadKey('p', 'b1'))).toBeTruthy())
    await waitFor(() => expect(tasks).toBe(1))
    return { client, tasks: () => tasks }
  }

  it('Landing checks -> Landing on the read refetches the board and the map', async () => {
    answer = read('checking', 'running')
    const { client, tasks } = await mount()
    answer = read('landing', 'passed')
    await act(async () => {
      await client.refetchQueries({ queryKey: buildReadKey('p', 'b1') })
    })
    await waitFor(() => expect(tasks()).toBe(2))
  })

  it('an unchanged read leaves the task list alone', async () => {
    answer = read('checking', 'running')
    const { client, tasks } = await mount()
    await act(async () => {
      await client.refetchQueries({ queryKey: buildReadKey('p', 'b1') })
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(tasks()).toBe(1)
  })
})
