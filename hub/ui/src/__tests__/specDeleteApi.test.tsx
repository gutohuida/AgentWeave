import { describe, expect, it, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useDeleteSpecDocument, useSpec } from '@/api/spec'
import { useConfigStore } from '@/store/configStore'

// F829: the page stayed on a deleted document and its per-document queries failed one by one,
// because the corpus invalidation refetched the dead path's own keys while the panel was mounted.
// The path's keys are left alone (a mounted observer rebuilds a removed query), and the document
// leaves the cached lists with the 200.
const GONE = 'spec/changes/ui-delete/spec.json'
const KEPT = 'spec/spec.json'

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

beforeEach(() => {
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-1',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})

describe('useDeleteSpecDocument', () => {
  it('stops asking for the deleted document and takes it out of the cached lists', async () => {
    const calls: string[] = []
    globalThis.fetch = ((url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? 'GET'} ${url}`)
      if (init?.method === 'DELETE') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ path: GONE, deleted: true, tasks: ['task-1'] }),
        } as Response)
      }
      if (url.includes(encodeURIComponent(GONE))) {
        return Promise.resolve({ ok: false, status: 404, json: async () => ({}) } as Response)
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['project', 'proj-1', 'specs'], {
      specs: [{ path: GONE }, { path: KEPT }],
      home: KEPT,
    })
    client.setQueryData(['project', 'proj-1', 'specDocuments'], {
      documents: [{ path: GONE }, { path: KEPT }],
    })
    client.setQueryData(['project', 'proj-1', 'spec', GONE], { path: GONE })

    // The panel is still mounted when the 200 lands, so the document's observer is live.
    const { result } = renderHook(() => ({ doc: useSpec(GONE), del: useDeleteSpecDocument() }), {
      wrapper: wrapper(client),
    })
    await waitFor(() => expect(calls.some((c) => c.includes(encodeURIComponent(GONE)))).toBe(true))
    calls.length = 0

    result.current.del.mutate({ path: GONE })
    await waitFor(() => expect(result.current.del.isSuccess).toBe(true))
    await new Promise((r) => setTimeout(r, 300))

    expect(calls.filter((c) => c.startsWith('GET') && c.includes(encodeURIComponent(GONE)))).toEqual([])
    const list = client.getQueryData<{ specs: { path: string }[] }>(['project', 'proj-1', 'specs'])
    expect(list?.specs.map((s) => s.path)).toEqual([KEPT])
    const docs = client.getQueryData<{ documents: { path: string }[] }>([
      'project',
      'proj-1',
      'specDocuments',
    ])
    expect(docs?.documents.map((d) => d.path)).toEqual([KEPT])
  })
})
