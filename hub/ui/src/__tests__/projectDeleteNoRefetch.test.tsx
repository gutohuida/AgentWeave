import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useDeleteProject } from '@/api/projects'

// F729: after a project delete the app refetched the deleted project -- ten-odd 404s before it
// navigated away. The delete wrote the store's selected project directly, App's
// destination->store effect (still holding the deleted destination for one commit) wrote the
// deleted id straight back, and every store-keyed query re-ran for a project that is gone.
// Real App, real `@/api/projects` hooks and real navigation; only the network and the page
// bodies are stubbed.

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const project = (id: string, name: string) => ({
  id, name, working_directory: `C:/work/${id}`, path_display: `C:/work/${id}`,
  directory_state: 'available', last_opened_at: null, last_seen_at: null, hop_budget: 20,
  turn_delivery_cap: 20, agent_budget: 10, token_budget: null, allow_agent_jobs: true, agents: [],
})

let deleted = false
const requests: string[] = []
vi.stubGlobal(
  'fetch',
  vi.fn(async (url: string, init?: RequestInit) => {
    const path = String(url).replace('http://hub.test', '')
    requests.push(`${init?.method ?? 'GET'} ${path}`)
    if (init?.method === 'DELETE') {
      deleted = true
      return { ok: true, status: 204, json: async () => ({}), text: async () => '' } as unknown as Response
    }
    if (path === '/api/v1/projects') {
      const body = deleted ? [project('proj-beta', 'Beta')] : [project('proj-alpha', 'Alpha'), project('proj-beta', 'Beta')]
      return { ok: true, status: 200, json: async () => body } as unknown as Response
    }
    if (deleted && path.includes('/projects/proj-alpha')) {
      return { ok: false, status: 404, json: async () => ({}), text: async () => '{"detail":"Project not found"}' } as unknown as Response
    }
    return { ok: true, status: 200, json: async () => [], text: async () => '[]' } as unknown as Response
  }),
)

vi.mock('@/components/overview/OverviewPage', () => ({ OverviewPage: () => <div data-testid="page-overview" /> }))
vi.mock('@/components/layout/StatusBar', () => ({ StatusBar: () => null }))
vi.mock('@/components/layout/SetupModal', () => ({ SetupModal: () => null }))

import App from '@/App'

function DeleteAlpha() {
  const remove = useDeleteProject('proj-alpha')
  return <button onClick={() => remove.mutate(false)}>delete alpha</button>
}

describe('deleting a project does not refetch it (F729)', () => {
  beforeEach(() => {
    cleanup()
    deleted = false
    requests.length = 0
    window.history.pushState(null, '', '/?project=proj-alpha&tab=overview')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-alpha',
      isConfigured: true,
      bootstrapState: 'ready',
      mode: 'light',
    })
  })

  it('never selects the deleted project again, and asks nothing more about it', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <App />
        <DeleteAlpha />
      </QueryClientProvider>,
    )
    await screen.findByTestId('page-overview')
    await waitFor(() => expect(requests).toContain('GET /api/v1/projects'))

    const selected: Array<string | null> = []
    const unsubscribe = useConfigStore.subscribe((state) => selected.push(state.selectedProjectId))
    const before = requests.length

    await act(async () => {
      fireEvent.click(screen.getByText('delete alpha'))
    })
    await waitFor(() => expect(useConfigStore.getState().selectedProjectId).toBe('proj-beta'))
    await waitFor(() => expect(window.location.search).toContain('project=proj-beta'))
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    unsubscribe()

    expect(selected).not.toContain('proj-alpha')
    const afterDelete = requests.slice(before).filter((r) => !r.startsWith('DELETE'))
    expect(afterDelete.filter((r) => r.includes('/projects/proj-alpha'))).toEqual([])
  })
})
