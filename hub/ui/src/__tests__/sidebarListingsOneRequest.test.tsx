import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useProjectConversations } from '@/api/agentChat'
import { useQueueStatuses } from '@/api/queue'
import { ApiError } from '@/api/client'
import { cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'

// Perf slice 4, R1: opening the app reads every sidebar project's conversations in one request,
// and every listed agent's queue status in one, instead of one request each. The per-key caches,
// invalidation and the single routes are unchanged: a key read on its own uses its own route.
const PROJECTS = Array.from({ length: 25 }, (_, i) => `proj-${i}`)
const AGENTS = ['a', 'b', 'c', 'd', 'e']
let gets: string[] = []
let oldHub = false

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const listing = (projectId: string) => ({
  conversations: [{ id: `conv-${projectId}`, agent: 'a' }],
  archived_count: 0,
  archived_by_agent: {},
})
const status = (agent: string) => ({ agent, waiting_count: 0, running: false, waiting_reason: null })

function installHub() {
  gets = []
  ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = new URL(String(input))
    if (url.pathname.endsWith('/api/v1/events')) {
      return new Response(new ReadableStream<Uint8Array>({ start() {} }), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      })
    }
    gets.push(url.pathname + url.search)
    if (url.pathname === '/api/v1/conversations' && !oldHub) {
      const ids = url.searchParams.getAll('project_id')
      const known = ids.filter((id) => id !== 'proj-gone')
      return json({
        projects: Object.fromEntries(known.map((id) => [id, listing(id)])),
        missing: ids.filter((id) => id === 'proj-gone'),
      })
    }
    const one = url.pathname.match(/^\/api\/v1\/projects\/([^/]+)\/conversations$/)
    if (one) return json(listing(one[1]))
    if (url.pathname === '/api/v1/projects/p/queue-status') {
      const agents = url.searchParams.getAll('agent')
      return json({ statuses: Object.fromEntries(agents.map((a) => [a, status(a)])), missing: [] })
    }
    const queue = url.pathname.match(/^\/api\/v1\/projects\/p\/queue\/([^/]+)\/status$/)
    if (queue) return json(status(queue[1]))
    return json({ detail: 'not in this fixture' }, 404)
  })
}

function Rail({ projects }: { projects: string[] }) {
  return (
    <>
      {projects.map((id) => (
        <Listing key={id} projectId={id} />
      ))}
    </>
  )
}

const errors: Record<string, unknown> = {}
function Listing({ projectId }: { projectId: string }) {
  const { error } = useProjectConversations(projectId)
  if (error) errors[projectId] = error
  return null
}

function Cards() {
  useQueueStatuses(AGENTS)
  return null
}

describe('the sidebar reads its listings in one request', () => {
  beforeEach(() => {
    __resetSSEStateForTest()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'p',
      isConfigured: true,
      bootstrapState: 'ready',
    })
    oldHub = false
    installHub()
  })

  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('25 projects are one request, and each listing is its own project’s', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Rail projects={PROJECTS} />
      </QueryClientProvider>,
    )
    await waitFor(() =>
      PROJECTS.forEach((id) => expect(client.getQueryData(['project', id, 'conversations', 'open'])).toBeTruthy()),
    )
    const listings = gets.filter((g) => g.includes('conversations'))
    expect(listings).toHaveLength(1)
    expect(listings[0]).toBe(`/api/v1/conversations?${PROJECTS.map((id) => `project_id=${id}`).join('&')}&lifecycle=open`)
    expect(client.getQueryData(['project', 'proj-7', 'conversations', 'open'])).toEqual(listing('proj-7'))

    // An event refreshing one project reads that project alone, from its own route.
    gets = []
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['project', 'proj-3', 'conversations'] })
    })
    expect(gets).toEqual(['/api/v1/projects/proj-3/conversations?lifecycle=open'])
  })

  it('a project the Hub no longer has fails as its own route would, and the rest still load', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Rail projects={['proj-1', 'proj-gone', 'proj-2']} />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(errors['proj-gone']).toBeTruthy())
    expect(errors['proj-gone']).toBeInstanceOf(ApiError)
    expect((errors['proj-gone'] as ApiError).status).toBe(404)
    await waitFor(() => expect(client.getQueryData(['project', 'proj-2', 'conversations', 'open'])).toBeTruthy())
    expect(gets.filter((g) => g.includes('conversations'))).toHaveLength(1)
  })

  it('a Hub without the many-project route still lists every project, one request each', async () => {
    // The committed bundle reaches the operator's app on reload, before their Hub restarts onto
    // the code that serves the new route.
    oldHub = true
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Rail projects={['proj-1', 'proj-2', 'proj-3']} />
      </QueryClientProvider>,
    )
    await waitFor(() =>
      ['proj-1', 'proj-2', 'proj-3'].forEach((id) =>
        expect(client.getQueryData(['project', id, 'conversations', 'open'])).toEqual(listing(id)),
      ),
    )
    expect(gets.filter((g) => g.startsWith('/api/v1/projects/'))).toHaveLength(3)
  })

  it('every listed agent’s queue status is one request', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Cards />
      </QueryClientProvider>,
    )
    await waitFor(() =>
      AGENTS.forEach((a) => expect(client.getQueryData(['project', 'p', 'queue', a, 'status'])).toEqual(status(a))),
    )
    expect(gets).toEqual([`/api/v1/projects/p/queue-status?${AGENTS.map((a) => `agent=${a}`).join('&')}`])
  })
})
