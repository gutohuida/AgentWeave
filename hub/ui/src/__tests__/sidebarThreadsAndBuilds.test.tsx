import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import { Sidebar } from '@/components/layout/Sidebar'
import { useConfigStore } from '@/store/configStore'

/** The sidebar's threads and builds as the app feeds them (profiles-threads-and-builds-everywhere
 *  FR-1, FR-3, FR-5, FR-14). The routes are stubbed at `fetch`, so the hooks, the coalesced
 *  conversation read, the build filter and the dismiss POST are the real ones. */

const project = (id: string, name: string, agents: Array<{ name: string; color_index: number }>) => ({
  id,
  name,
  working_directory: `C:/work/${id}`,
  path_display: `C:/work/${id}`,
  directory_state: 'available',
  last_opened_at: null,
  last_seen_at: null,
  hop_budget: 20,
  turn_delivery_cap: 20,
  agent_budget: 10,
  token_budget: null,
  allow_agent_jobs: true,
  agents: agents.map((a) => ({ id: `agent-${a.name}`, status: 'idle', last_seen: null, ...a })),
})

let projects = [project('proj-a', 'Website', [{ name: 'Architect', color_index: 0 }, { name: 'QA', color_index: 2 }])]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

function thread(id: string, agent: string, title: string, activity: string, extra: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id,
    agent,
    provider_session_id: null,
    lifecycle: 'open',
    title,
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-11-20T08:00:00Z',
    updated_at: activity,
    last_activity_at: activity,
    operator_thread: true,
    ...extra,
  }
}

function build(id: string, title: string, extra: Partial<ProjectBuildRow> = {}): ProjectBuildRow {
  return {
    id,
    document_id: `doc-${id}`,
    document_title: title,
    state: 'running',
    driver: 'flow',
    level: 'reviewed',
    lead: null,
    loop_id: null,
    loop: null,
    tasks_total: 9,
    tasks_done: 3,
    tasks_landing: 0,
    landings: [],
    spent_usd: null,
    stop_reason: null,
    created_at: '2026-11-20T08:00:00Z',
    stopped_at: null,
    needs_operator: null,
    attention_dismissed: false,
    open_questions: 0,
    question: null,
    ...extra,
  }
}

// Four operator threads of two profiles, newest `last_activity_at` first: the order
// `operator_threads=true` returns (agent_chat.py, `_project_conversations`). The waiting one is
// the third newest.
const ROUTE_THREADS = [
  thread('conv-1', 'Architect', 'Spec: profiles', '2026-11-20T12:00:00Z', { attention: 'running' }),
  thread('conv-2', 'QA', 'Drive the vault', '2026-11-20T11:00:00Z'),
  thread('conv-3', 'QA', 'Why did the landing hold?', '2026-11-20T10:00:00Z', { attention: 'waiting' }),
  thread('conv-4', 'Architect', 'Roadmap: role profiles', '2026-11-20T09:00:00Z'),
]

let open: Record<string, ProjectConversations>
let archived: Record<string, ProjectConversations>
let builds: Record<string, ProjectBuildRow[] | 'error'>
let conversationsFail: boolean
const requests: Array<{ url: string; method: string }> = []

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

const listing = (conversations: AgentConversation[], archivedCount = 0): ProjectConversations => ({
  conversations,
  archived_count: archivedCount,
  archived_by_agent: {},
})

beforeEach(() => {
  localStorage.clear()
  requests.length = 0
  conversationsFail = false
  projects = [project('proj-a', 'Website', [{ name: 'Architect', color_index: 0 }, { name: 'QA', color_index: 2 }])]
  open = { 'proj-a': listing(ROUTE_THREADS) }
  archived = { 'proj-a': listing([]) }
  builds = { 'proj-a': [] }
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init?: RequestInit) => {
      const url = new URL(String(input), 'http://hub')
      requests.push({ url: url.pathname + url.search, method: init?.method ?? 'GET' })
      const lifecycle = url.searchParams.get('lifecycle')
      const source = lifecycle === 'archived' ? archived : open
      if (url.pathname === '/api/v1/conversations') {
        if (conversationsFail) return respond(500, { detail: 'boom' })
        const ids = url.searchParams.getAll('project_id')
        return respond(200, { projects: Object.fromEntries(ids.map((id) => [id, source[id]])), missing: [] })
      }
      const one = url.pathname.match(/^\/api\/v1\/projects\/([^/]+)\/conversations$/)
      if (one) return conversationsFail ? respond(500, { detail: 'boom' }) : respond(200, source[one[1]])
      const dismiss = url.pathname.match(/^\/api\/v1\/projects\/([^/]+)\/project\/builds\/([^/]+)\/attention\/dismiss$/)
      if (dismiss && init?.method === 'POST') {
        const rows = builds[dismiss[1]]
        if (rows === 'error') return respond(500, {})
        const row = rows.find((b) => b.id === dismiss[2])!
        if (row.state === 'running') return respond(409, { detail: { code: 'build_running' } })
        row.attention_dismissed = true
        return respond(200, row)
      }
      const list = url.pathname.match(/^\/api\/v1\/projects\/([^/]+)\/project\/builds$/)
      if (list) {
        const rows = builds[list[1]]
        return rows === 'error' ? respond(500, { detail: 'boom' }) : respond(200, { builds: rows ?? [] })
      }
      return respond(404, { detail: 'Not Found' })
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderRail(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    onOpenProject: vi.fn(),
    onOpenConversation: vi.fn(),
    onNewConversation: vi.fn(),
    onOpenBuild: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onAddProject: vi.fn(),
    ...overrides,
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <Sidebar {...props} />
    </QueryClientProvider>,
  )
  return { ...view, props }
}

const threadIds = (projectId = 'proj-a') =>
  within(screen.getByTestId(`rail-threads-${projectId}`))
    .queryAllByTestId(/^rail-thread-conv-[0-9]+$/)
    .map((row) => row.getAttribute('data-testid')!.replace('rail-thread-', ''))

describe('the sidebar lists the operator’s threads (FR-1)', () => {
  it('threads-recency-labelled: waiting first, then most recent activity, each naming its profile', async () => {
    renderRail()
    await screen.findByTestId('rail-thread-conv-1')
    expect(threadIds()).toEqual(['conv-3', 'conv-1', 'conv-2', 'conv-4'])
    // One list, no agent tree: no agent rows, no view toggle.
    expect(screen.queryByTestId(/^agent-expander-/)).toBeNull()
    expect(screen.queryByTestId('rail-view-toggle')).toBeNull()
    for (const [id, profile] of [['conv-1', 'Architect'], ['conv-2', 'QA'], ['conv-3', 'QA'], ['conv-4', 'Architect']]) {
      expect(screen.getByTestId(`rail-thread-${id}`)).toHaveTextContent(profile)
    }
    // It reads the operator's threads, not every conversation of the project.
    expect(requests.some((r) => r.url.includes('/conversations') && r.url.includes('operator_threads=true'))).toBe(true)
    expect(requests.some((r) => r.url.includes('/conversations') && !r.url.includes('operator_threads=true'))).toBe(false)
  })

  it('threads-recency-labelled: reversing the route’s order does not change the order shown', async () => {
    open = { 'proj-a': listing([...ROUTE_THREADS].reverse()) }
    renderRail()
    await screen.findByTestId('rail-thread-conv-1')
    expect(threadIds()).toEqual(['conv-3', 'conv-1', 'conv-2', 'conv-4'])
  })

  it('threads-archived-hidden: an archived thread is hidden until Show archived', async () => {
    const old = thread('conv-old', 'QA', 'Trial Hub smoke test', '2026-11-01T09:00:00Z', { lifecycle: 'archived' })
    open = { 'proj-a': listing(ROUTE_THREADS, 1) }
    archived = { 'proj-a': listing([old], 1) }
    renderRail()
    await screen.findByTestId('rail-thread-conv-1')
    expect(screen.queryByText('Trial Hub smoke test')).toBeNull()
    expect(requests.some((r) => r.url.includes('lifecycle=archived'))).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Show archived (1)' }))
    expect(await screen.findByTestId('rail-thread-archived-conv-old')).toHaveTextContent('Trial Hub smoke test')
  })

  it('opens a thread with its own profile', async () => {
    const { props } = renderRail()
    fireEvent.click(await screen.findByTestId('rail-thread-conv-3'))
    expect(props.onOpenConversation).toHaveBeenCalledWith('proj-a', 'QA', 'conv-3')
  })

  it('start-thread: New thread opens the new-thread surface with no profile implied', async () => {
    const { props } = renderRail()
    fireEvent.click(await screen.findByRole('button', { name: 'New thread' }))
    expect(props.onNewConversation).toHaveBeenCalledWith('proj-a', null)
  })

  it('says it could not load the threads, never an empty list, and Try again refetches', async () => {
    conversationsFail = true
    renderRail()
    const error = await screen.findByTestId('rail-threads-error-proj-a')
    expect(error).toHaveTextContent('Couldn’t load threads.')
    expect(screen.queryByTestId('rail-threads-empty-proj-a')).toBeNull()

    conversationsFail = false
    fireEvent.click(within(error).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('rail-thread-conv-1')).toBeInTheDocument()
  })
})

describe('the sidebar lists builds that are running or need the operator (FR-3)', () => {
  const running = build('build-run', 'Profiles, threads and builds')
  const stopped = () =>
    build('build-stop', 'The build dialog redesigned', {
      state: 'stopped',
      tasks_done: 4,
      tasks_total: 6,
      needs_operator: { kind: 'stopped', text: 'Stopped by you with 2 tasks not approved.' },
    })
  const finished = build('build-done', 'Vault importer', { state: 'finished', tasks_done: 4, tasks_total: 4 })

  it('builds-listed: the stopped build first, both titled with their states; the finished one is not', async () => {
    // Newest first, as `GET /project/builds` returns them: the running one is newest.
    builds = { 'proj-a': [running, stopped(), finished] }
    const { props } = renderRail()
    await screen.findByTestId('rail-build-build-run')
    const rows = within(screen.getByTestId('rail-builds-proj-a')).getAllByTestId(/^rail-build-build-/)
      .filter((row) => !row.getAttribute('data-testid')!.includes('dismiss'))
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual(['rail-build-build-stop', 'rail-build-build-run'])
    expect(screen.getByRole('button', { name: 'Build: The build dialog redesigned, 4 of 6 tasks done, stopped, needs you' })).toHaveTextContent('Stopped')
    expect(screen.getByRole('button', { name: 'Build: Profiles, threads and builds, 3 of 9 tasks done, running' })).toHaveTextContent('3/9')
    expect(screen.queryByText('Vault importer')).toBeNull()
    expect(screen.queryByRole('link', { name: /all builds/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /all builds/i })).toBeNull()

    fireEvent.click(screen.getByTestId('rail-build-build-stop'))
    expect(props.onOpenBuild).toHaveBeenCalledWith('proj-a', 'build-stop')
  })

  it('build-dismissed: a running build offers no dismiss; a dismissed one leaves and stays gone after reload', async () => {
    builds = { 'proj-a': [running, stopped()] }
    const first = renderRail()
    await screen.findByTestId('rail-build-build-stop')
    expect(screen.queryByTestId('rail-build-dismiss-build-run')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss build: The build dialog redesigned' }))
    await waitFor(() => expect(screen.queryByTestId('rail-build-build-stop')).toBeNull())
    expect(requests).toContainEqual({ url: '/api/v1/projects/proj-a/project/builds/build-stop/attention/dismiss', method: 'POST' })
    expect(screen.getByTestId('rail-build-build-run')).toBeInTheDocument()

    // Reload: a fresh cache reads the Hub again, which still reports it dismissed.
    first.unmount()
    renderRail()
    await screen.findByTestId('rail-build-build-run')
    expect(screen.queryByTestId('rail-build-build-stop')).toBeNull()
  })

  it('build-dismissed: once restarted, a dismissed build is listed again because it is running', async () => {
    builds = { 'proj-a': [{ ...stopped(), attention_dismissed: true }] }
    const first = renderRail()
    await waitFor(() => expect(requests.some((r) => r.url.endsWith('/project/builds'))).toBe(true))
    expect(screen.queryByTestId('rail-build-build-stop')).toBeNull()
    first.unmount()

    // Restarted, and one of its tasks stalls: running, with a need.
    builds = {
      'proj-a': [
        build('build-stop', 'The build dialog redesigned', {
          needs_operator: { kind: 'stalled', text: 'PTBE-4 stalled.' },
          attention_dismissed: true,
        }),
      ],
    }
    renderRail()
    expect(await screen.findByTestId('rail-build-build-stop')).toHaveAttribute('data-state', 'running')
    expect(screen.queryByTestId('rail-build-dismiss-build-stop')).toBeNull()
  })

  it('says it could not load the builds, and Try again refetches', async () => {
    builds = { 'proj-a': 'error' }
    renderRail()
    const error = await screen.findByTestId('rail-builds-error-proj-a')
    builds = { 'proj-a': [running] }
    fireEvent.click(within(error).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByTestId('rail-build-build-run')).toBeInTheDocument()
  })
})

describe('the collapsed sidebar shows projects only (FR-14)', () => {
  it('compact-rail-marked: no profile icons; the project with a stopped build is marked and says so', async () => {
    projects = [
      project('proj-a', 'Website', [{ name: 'Architect', color_index: 0 }]),
      project('proj-b', 'Bakery', [{ name: 'QA', color_index: 2 }]),
    ]
    open = { 'proj-a': listing([]), 'proj-b': listing([]) }
    builds = {
      'proj-a': [
        build('build-stop', 'The build dialog redesigned', {
          state: 'stopped',
          needs_operator: { kind: 'stopped', text: 'Stopped.' },
        }),
      ],
      'proj-b': [build('build-run', 'Profiles, threads and builds')],
    }
    renderRail({ compact: true })

    expect(await screen.findByTestId('rail-compact-needs-proj-a')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Projects' })
    expect(within(nav).getAllByRole('button').map((b) => b.getAttribute('data-testid'))).toEqual([
      'rail-compact-project-proj-a',
      'rail-compact-project-proj-b',
    ])
    expect(screen.queryByTestId(/^rail-compact-agent-/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Website: 1 build needs you' })).toBeInTheDocument()
    await waitFor(() => expect(requests.some((r) => r.url === '/api/v1/projects/proj-b/project/builds')).toBe(true))
    expect(screen.getByRole('button', { name: 'Bakery' })).toBeInTheDocument()
    expect(screen.queryByTestId('rail-compact-needs-proj-b')).toBeNull()
  })
})
