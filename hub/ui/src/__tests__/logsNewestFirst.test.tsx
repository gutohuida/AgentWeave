import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EventLogEntry } from '@/api/logs'
import { useConfigStore } from '@/store/configStore'

// F252. The Logs screen fetched the route's oldest 500 entries and could never show a newer one.
// The route now answers newest first with `offset` counting back, and the hook pages backwards.
// The fake below answers in that order, from a log of seven entries.

const getJson = vi.fn()
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, getJson: (path: string) => getJson(path) }
})
vi.mock('@/hooks/useSSE', () => ({ useSSE: () => undefined }))

import { useLogs } from '@/api/logs'

function entry(n: number): EventLogEntry {
  return {
    id: `log-${n}`,
    project_id: 'proj-test',
    event_type: `event_${n}`,
    severity: 'info',
    timestamp: new Date(Date.UTC(2026, 8, 23, 12, 0, n)).toISOString(),
  }
}

// Oldest to newest, as they happened.
const LOG = [0, 1, 2, 3, 4, 5, 6].map(entry)

function routeAnswer(path: string): EventLogEntry[] {
  const query = new URLSearchParams(path.split('?')[1])
  const limit = Number(query.get('limit'))
  const offset = Number(query.get('offset') ?? 0)
  return [...LOG].reverse().slice(offset, offset + limit)
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('the Logs screen reads the newest entries first (F252)', () => {
  beforeEach(() => {
    getJson.mockReset()
    getJson.mockImplementation(async (path: string) => routeAnswer(path))
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY123',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
    })
  })

  it('opens on the newest page, in time order', async () => {
    const { result } = renderHook(() => useLogs({ limit: 3 }), { wrapper })

    await waitFor(() => expect(result.current.data).toBeDefined())
    expect(result.current.data?.map((e) => e.id)).toEqual(['log-4', 'log-5', 'log-6'])
    expect(result.current.hasOlder).toBe(true)
    expect(getJson.mock.calls[0][0]).toContain('offset=0')
  })

  it('pages back to older entries, and stops at the start of the log', async () => {
    const { result } = renderHook(() => useLogs({ limit: 3 }), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())

    await act(async () => { await result.current.loadOlder() })
    await waitFor(() => expect(result.current.data).toHaveLength(6))
    expect(result.current.data?.map((e) => e.id)).toEqual([
      'log-1', 'log-2', 'log-3', 'log-4', 'log-5', 'log-6',
    ])

    await act(async () => { await result.current.loadOlder() })
    await waitFor(() => expect(result.current.data).toHaveLength(7))
    expect(result.current.data?.[0].id).toBe('log-0')
    expect(result.current.hasOlder).toBe(false)
  })
})
