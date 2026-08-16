import { describe, expect, it, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useTasks, useDocumentTasks } from '@/api/tasks'
import { useConfigStore } from '@/store/configStore'

/**
 * `useTasks({ excludeArchivedCompleted })` and `useDocumentTasks(documentId)` — the two request
 * shapes `2026-08-16-the-board-scoped-by-document` adds to `GET /tasks`. `TasksBoard.tsx`'s own
 * behaviour is covered by `tasksBoardFilter.test.tsx`; this file holds the hooks to the exact
 * request each option produces.
 */

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

describe('useTasks', () => {
  it('requests the bare path with no argument', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => [] } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTasks(), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual(['http://hub.test/api/v1/projects/proj-1/tasks'])
  })

  it('requests ?exclude_archived_completed=true when asked', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => [] } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTasks({ excludeArchivedCompleted: true }), {
      wrapper: wrapper(client),
    })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks?exclude_archived_completed=true',
    ])
  })
})

describe('useDocumentTasks', () => {
  it('requests ?spec_document_id=<id>', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => [] } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useDocumentTasks('spdoc-1'), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks?spec_document_id=spdoc-1',
    ])
  })

  it('does not fire when given no document id', async () => {
    const fetchSpy = vi.fn()
    globalThis.fetch = fetchSpy as unknown as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    renderHook(() => useDocumentTasks(null), { wrapper: wrapper(client) })
    await new Promise((r) => setTimeout(r, 0))

    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
