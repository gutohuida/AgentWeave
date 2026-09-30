import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useCreateRunner, useDeleteRunner, useUpdateRunner } from '@/api/runners'
import { useConfigStore } from '@/store/configStore'

/**
 * Editing a runner re-reads the agents' launchability verdict (design D6 of
 * `a-runner-that-cannot-collaborate-says-so-where-it-is-bound`). A bound agent's verdict is read
 * from its runner, and lives under the `agents` prefix with a 30 s stale time, so invalidating
 * `runners` alone left a fixed warning standing. Creating or deleting a runner cannot change any
 * agent's verdict: a new runner has no agent, and the Hub refuses to delete one that has (409,
 * `runners.py` `delete_runner`), so neither re-reads it.
 */

const AGENTS_LAUNCHABILITY = ['project', 'proj-1', 'agents', 'launchability']
const RUNNERS = ['project', 'proj-1', 'runners']

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function invalidatedKeys(spy: ReturnType<typeof vi.spyOn>): unknown[] {
  return spy.mock.calls.map((call: unknown[]) => (call[0] as { queryKey?: unknown }).queryKey)
}

beforeEach(() => {
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-1',
    isConfigured: true,
    bootstrapState: 'ready',
  })
  globalThis.fetch = (() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ id: 'r1', name: 'r', cli: 'codex', flags: [] }),
    } as Response)) as typeof fetch
})

describe('runner mutations and the agents launchability verdict', () => {
  it('editing a runner invalidates the agents launchability verdict', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useUpdateRunner(), { wrapper: wrapper(client) })

    await result.current.mutateAsync({ id: 'r1', updates: { name: 'renamed' } })

    expect(invalidatedKeys(spy)).toContainEqual(RUNNERS)
    expect(invalidatedKeys(spy)).toContainEqual(AGENTS_LAUNCHABILITY)
  })

  it('deleting a runner leaves the agents verdict alone: only an unbound runner can be deleted', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useDeleteRunner(), { wrapper: wrapper(client) })

    await result.current.mutateAsync('r1')

    expect(invalidatedKeys(spy)).toContainEqual(RUNNERS)
    expect(invalidatedKeys(spy)).not.toContainEqual(AGENTS_LAUNCHABILITY)
  })

  it('creating a runner leaves the agents verdict alone: no agent is bound to it yet', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const spy = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useCreateRunner(), { wrapper: wrapper(client) })

    await result.current.mutateAsync({ name: 'r', cli: 'codex' } as never)

    expect(invalidatedKeys(spy)).toContainEqual(RUNNERS)
    expect(invalidatedKeys(spy)).not.toContainEqual(AGENTS_LAUNCHABILITY)
  })
})
