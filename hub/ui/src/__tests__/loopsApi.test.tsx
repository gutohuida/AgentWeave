import { describe, expect, it, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useStopLoop, useArchiveLoop, useSetLoopControl } from '@/api/loops'
import { useConfigStore } from '@/store/configStore'

/**
 * The three loop-tab mutations (`a-loop-is-stopped-archived-and-delegated-from-its-own-tab`, task
 * 1.14): the exact request each produces, and that each re-reads the loop and the job list even
 * when the Hub refuses (`onSettled`, not `onSuccess`) — a refused Stop that lost a race is exactly
 * the case where the tab must show what the Hub recorded.
 */

interface Recorded {
  url: string
  method?: string
  body?: string
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function recordFetch(respond: () => Response): Recorded[] {
  const seen: Recorded[] = []
  globalThis.fetch = ((url: string, init?: RequestInit) => {
    seen.push({ url, method: init?.method, body: init?.body as string | undefined })
    return Promise.resolve(respond())
  }) as typeof fetch
  return seen
}

const OK = () => ({ ok: true, status: 200, json: async () => ({}), text: async () => '{}' }) as Response

const REFUSED_BODY = JSON.stringify({
  detail: { code: 'loop_already_ended', message: 'this loop already ended (enough)' },
})
const REFUSED = () =>
  ({
    ok: false,
    status: 409,
    statusText: 'Conflict',
    json: async () => JSON.parse(REFUSED_BODY),
    text: async () => REFUSED_BODY,
  }) as Response

beforeEach(() => {
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-1',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})

const BASE = 'http://hub.test/api/v1/projects/proj-1'

describe('loop mutations — the request each sends', () => {
  it('useStopLoop PATCHes the job with only stop_reason', async () => {
    const seen = recordFetch(OK)
    const client = new QueryClient()
    const { result } = renderHook(() => useStopLoop(), { wrapper: wrapper(client) })
    await result.current.mutateAsync({ jobId: 'job-1', reason: 'enough' })

    expect(seen).toHaveLength(1)
    expect(seen[0].url).toBe(`${BASE}/jobs/job-1`)
    expect(seen[0].method).toBe('PATCH')
    expect(JSON.parse(seen[0].body as string)).toEqual({ stop_reason: 'enough' })
  })

  it('useArchiveLoop POSTs to the loop archive route', async () => {
    const seen = recordFetch(OK)
    const client = new QueryClient()
    const { result } = renderHook(() => useArchiveLoop(), { wrapper: wrapper(client) })
    await result.current.mutateAsync({ loopId: 'loop-1' })

    expect(seen[0].url).toBe(`${BASE}/loops/loop-1/archive`)
    expect(seen[0].method).toBe('POST')
  })

  it('useSetLoopControl POSTs the control to the loop control route', async () => {
    const seen = recordFetch(OK)
    const client = new QueryClient()
    const { result } = renderHook(() => useSetLoopControl(), { wrapper: wrapper(client) })
    await result.current.mutateAsync({ loopId: 'loop-1', control: 'creator' })

    expect(seen[0].url).toBe(`${BASE}/loops/loop-1/control`)
    expect(seen[0].method).toBe('POST')
    expect(JSON.parse(seen[0].body as string)).toEqual({ control: 'creator' })
  })
})

describe('loop mutations — invalidate on settle, refused or not', () => {
  const calls: Array<[string, (r: ReturnType<typeof useStopLoop | typeof useArchiveLoop | typeof useSetLoopControl>) => Promise<unknown>, () => unknown]> = [
    ['useStopLoop', (r) => (r as ReturnType<typeof useStopLoop>).mutateAsync({ jobId: 'job-1', reason: 'x' }), () => useStopLoop()],
    ['useArchiveLoop', (r) => (r as ReturnType<typeof useArchiveLoop>).mutateAsync({ loopId: 'loop-1' }), () => useArchiveLoop()],
    [
      'useSetLoopControl',
      (r) => (r as ReturnType<typeof useSetLoopControl>).mutateAsync({ loopId: 'loop-1', control: 'operator' }),
      () => useSetLoopControl(),
    ],
  ]

  for (const [name, call, hook] of calls) {
    it(`${name} still invalidates loops and jobs when the Hub answers 409`, async () => {
      recordFetch(REFUSED)
      const client = new QueryClient()
      const invalidated: unknown[] = []
      const original = client.invalidateQueries.bind(client)
      client.invalidateQueries = ((filters: unknown) => {
        invalidated.push(filters)
        return original(filters as never)
      }) as typeof client.invalidateQueries

      const { result } = renderHook(() => hook() as never, { wrapper: wrapper(client) })
      await expect(call(result.current)).rejects.toBeDefined()

      expect(invalidated).toContainEqual({ queryKey: ['project', 'proj-1', 'loops'] })
      expect(invalidated).toContainEqual({ queryKey: ['project', 'proj-1', 'jobs'] })
    })
  }
})
