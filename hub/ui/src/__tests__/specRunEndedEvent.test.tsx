import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

/* A recording run's end arrives as `spec_updated {run_ended}` with neither `path` nor `evidence`.
 * It has to refetch the coverage bar and the evidence rows — that is what un-greys a piece held as
 * still being recorded — and it has to throw nothing on the missing fields. */

let handler: ((event: { type: string; data: unknown }) => void) | null = null
vi.mock('@/hooks/useSSE', () => ({
  useSSE: (fn: (event: { type: string; data: unknown }) => void) => {
    handler = fn
  },
}))

import { useSpecEvents } from '@/api/spec'

describe('spec_updated with only run_ended', () => {
  beforeEach(() => {
    handler = null
    useConfigStore.setState({ selectedProjectId: 'proj-a', isConfigured: true })
  })

  it('invalidates coverage and evidence and throws nothing', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    renderHook(() => useSpecEvents(), { wrapper })
    expect(() =>
      handler!({ type: 'spec_updated', data: { run_ended: 'run-1', project_id: 'proj-a' } }),
    ).not.toThrow()
    const keys = spy.mock.calls.map((c) =>
      JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey),
    )
    expect(keys).toContain(JSON.stringify(['project', 'proj-a', 'specCoverage']))
    expect(keys).toContain(JSON.stringify(['project', 'proj-a', 'specEvidence']))
  })
})
