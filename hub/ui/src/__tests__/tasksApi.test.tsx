import { describe, expect, it, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { useTasks, useDocumentTasks, useTaskBoard, useRenameTask } from '@/api/tasks'
import { useConfigStore } from '@/store/configStore'

/**
 * `useTasks({ excludeArchivedCompleted })` and `useDocumentTasks(documentId)` — the two request
 * shapes `2026-08-16-the-board-scoped-by-document` adds to `GET /tasks`. `TasksBoard.tsx`'s own
 * behaviour is covered by `tasksBoardFilter.test.tsx`; this file holds the hooks to the exact
 * request each option produces.
 */

/** The envelope `GET /tasks` answers with since F202. */
const PAGE = { tasks: [], total: 0, has_more: false }

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
      return Promise.resolve({ ok: true, status: 200, json: async () => PAGE } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTasks(), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual(['http://hub.test/api/v1/projects/proj-1/tasks?limit=1000'])
  })

  it('requests ?exclude_archived_completed=true when asked', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => PAGE } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTasks({ excludeArchivedCompleted: true }), {
      wrapper: wrapper(client),
    })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks?exclude_archived_completed=true&limit=1000',
    ])
  })

  it('requests ?loop_id=<id> when asked, taking priority over excludeArchivedCompleted', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => PAGE } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(
      () => useTasks({ loopId: 'loop-1', excludeArchivedCompleted: true }),
      { wrapper: wrapper(client) },
    )
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks?loop_id=loop-1&limit=1000',
    ])
  })
})

describe('useDocumentTasks', () => {
  it('requests ?spec_document_id=<id>', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({ ok: true, status: 200, json: async () => PAGE } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useDocumentTasks('spdoc-1'), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks?spec_document_id=spdoc-1&limit=1000',
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

describe('useRenameTask', () => {
  // F125, `the-operator-can-rename-a-task`, design D4: the PATCH body is exactly `{title}` — never
  // `status`, which `useUpdateTask` always sends and which the route would restate on a `blocked`
  // task without `blocked_reason`.
  it('PATCHes exactly {title}, nothing else', async () => {
    let seenUrl = ''
    let seenMethod = ''
    let seenBody: unknown = null
    globalThis.fetch = ((url: string, init?: RequestInit) => {
      seenUrl = url
      seenMethod = String(init?.method)
      seenBody = JSON.parse(String(init?.body))
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ id: 'task-1', title: 'New name' }),
      } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useRenameTask(), { wrapper: wrapper(client) })
    result.current.mutate({ id: 'task-1', title: 'New name' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(seenUrl).toBe('http://hub.test/api/v1/projects/proj-1/tasks/task-1')
    expect(seenMethod).toBe('PATCH')
    expect(seenBody).toEqual({ title: 'New name' })
  })
})

describe('useTaskBoard', () => {
  it('requests the bare path for a document id', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ spec_document_id: 'spdoc-1', tasks: [], edges: [] }),
      } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTaskBoard('spdoc-1'), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual([
      'http://hub.test/api/v1/projects/proj-1/tasks/board?spec_document_id=spdoc-1',
    ])
  })

  // `null` names the standing "no document" board (design D9) — not "nothing selected" — so
  // unlike `useDocumentTasks(null)` this fires, requesting the bare `/tasks/board` path the
  // backend reads as "spec_document_id is None" (`hub/hub/api/v1/tasks.py::task_board`).
  it('fires with no query string for the standing no-document board', async () => {
    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ spec_document_id: null, tasks: [], edges: [] }),
      } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useTaskBoard(null), { wrapper: wrapper(client) })
    await waitFor(() => expect(result.current.data).toBeDefined())

    expect(seen).toEqual(['http://hub.test/api/v1/projects/proj-1/tasks/board'])
  })
})
