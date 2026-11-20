import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { loadAllScreens } from '@/lib/lazyScreens'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

/** `every-spec-entry-point-leads-into-the-journey`, FR-11 / FR-12: a conversation owns its
 *  document. The Hub holds it; the app opens a conversation with it, writes it when a document is
 *  opened or exploring stops, and never carries it to another conversation or a new one. */

vi.mock('@/api/reopeningWarnings', () => ({
  useReopeningWarnings: () => ({ data: [], error: null }),
  useStopReopenedBuild: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissReopeningWarning: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/hooks/useSSE', () => ({
  // The rail's live dot reads this; a whole-module mock has to carry it or Sidebar throws.
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))


// What the Hub holds, per conversation; the PUTs the app made.
const held: Record<string, string | null> = {}
const puts: Array<{ conversation: string; path: string | null }> = []
const attached = (path: string | null) => ({
  attached: path ? { path, title: path, phase: 'exploring', step: null } : null,
  offers: [],
})

vi.stubGlobal(
  'fetch',
  vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response
    const m = /conversations\/([^/]+)\/spec-document(s?)$/.exec(url)
    if (m && m[2] === 's') return json(attached(held[m[1]] ?? null))
    if (m && init?.method === 'PUT') {
      const path = JSON.parse(String(init.body)).path as string | null
      held[m[1]] = path
      puts.push({ conversation: m[1], path })
      return json(attached(path))
    }
    return json([])
  }),
)

vi.mock('@/api/projects', () => ({
  useProjects: () => ({
    data: [{
      id: 'proj-test', name: 'AgentWeave', working_directory: 'C:/work/AgentWeave',
      path_display: 'C:/work/AgentWeave', directory_state: 'available', last_opened_at: null,
      last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
      token_budget: null, allow_agent_jobs: true,
      agents: [
        { id: 'agent-claude', name: 'claude', color_index: 2, status: 'idle', last_seen: null },
        { id: 'agent-codex', name: 'codex', color_index: 4, status: 'idle', last_seen: null },
      ],
    }, {
      id: 'proj-other', name: 'Client work', working_directory: 'C:/work/client',
      path_display: 'C:/work/client', directory_state: 'available', last_opened_at: null,
      last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
      token_budget: null, allow_agent_jobs: true, agents: [],
    }],
    isLoading: false,
  }),
  fetchProjectSummaries: vi.fn(async () => [{ id: 'proj-test' }]),
  useOpenProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useCreateProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useProjectSettings: () => ({ data: undefined, isError: false, error: null }),
  useUpdateProjectSettings: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRelocateProject: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRepositoryPreview: () => ({ data: undefined, error: null, refetch: vi.fn() }),
  useMakeRepository: () => ({ mutate: vi.fn(), reset: vi.fn(), isPending: false, error: null }),
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({
    data: [
      { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2 },
      { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, color_index: 4 },
    ],
    isLoading: false,
  }),
}))

vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({
    data: [
      { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2 },
      { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, color_index: 4 },
    ],
    isLoading: false,
  }),
}))
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({ data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }),
  useSpecEvents: () => {},
}))
vi.mock('@/components/agents/NewConversationSurface', () => ({
  NewConversationSurface: () => <div data-testid="new-conversation" />,
}))
vi.mock('@/components/layout/SetupModal', () => ({ SetupModal: () => null }))
// The conversation view, reduced to what the app hands it and the controls that act on it.
vi.mock('@/components/agents/ConversationView', () => ({
  ConversationView: (props: {
    agent: { name: string }
    conversationId: string | null
    document: string | null
    onSelectConversation: (id: string) => void
    onOpenAgentConversation: (agent: string, id: string) => void
    onOpenDocument: (path: string | null) => void
  }) => (
    <div data-testid="conv" data-id={props.conversationId} data-document={props.document ?? ''}>
      <button onClick={() => props.onOpenDocument('spec/changes/x/spec.json')}>open X</button>
      <button onClick={() => props.onOpenDocument(null)}>stop exploring</button>
      <button onClick={() => props.onSelectConversation('conv-b')}>to B</button>
      <button onClick={() => props.onOpenAgentConversation('codex', 'conv-c')}>to C</button>
    </div>
  ),
}))

import App from '@/App'

const X = 'spec/changes/x/spec.json'
const shown = () => screen.getByTestId('conv').getAttribute('data-document')

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

beforeAll(() => loadAllScreens(), 90000)

describe('a conversation owns its document', () => {
  beforeEach(() => {
    cleanup()
    for (const k of Object.keys(held)) delete held[k]
    puts.length = 0
    window.history.pushState(null, '', '?project=proj-test&agent=claude&conversation=conv-a')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-test',
      isConfigured: true, bootstrapState: 'ready', mode: 'light',
    })
  })

  it('reopened-conversation-restores-its-document: opens with the document the Hub holds', async () => {
    held['conv-a'] = X
    mount()
    await waitFor(() => expect(shown()).toBe(X))
    expect(window.location.search).toContain('document=')
  })

  it('opening a document writes it to the conversation', async () => {
    mount()
    await waitFor(() => expect(screen.getByTestId('conv')).toBeInTheDocument())
    fireEvent.click(screen.getByText('open X'))
    await waitFor(() => expect(shown()).toBe(X))
    expect(puts).toEqual([{ conversation: 'conv-a', path: X }])
  })

  it('stop-exploring-clears-the-document: writes null, and reopening shows none', async () => {
    held['conv-a'] = X
    mount()
    await waitFor(() => expect(shown()).toBe(X))
    fireEvent.click(screen.getByText('stop exploring'))
    await waitFor(() => expect(shown()).toBe(''))
    expect(held['conv-a']).toBeNull()
    cleanup()
    window.history.pushState(null, '', '?project=proj-test&agent=claude&conversation=conv-a')
    mount()
    await waitFor(() => expect(screen.getByTestId('conv')).toBeInTheDocument())
    await new Promise((r) => setTimeout(r, 50))
    expect(shown()).toBe('')
  })

  it('switching-conversation-drops-the-document: B shows none', async () => {
    held['conv-a'] = X
    mount()
    await waitFor(() => expect(shown()).toBe(X))
    fireEvent.click(screen.getByText('to B'))
    await waitFor(() => expect(screen.getByTestId('conv').getAttribute('data-id')).toBe('conv-b'))
    await new Promise((r) => setTimeout(r, 50))
    expect(shown()).toBe('')
    expect(window.location.search).not.toContain('document=')
    expect(held['conv-a']).toBe(X)
    expect(puts).toEqual([])
  })

  it('switching to another agent conversation shows that conversation own document', async () => {
    held['conv-a'] = X
    mount()
    await waitFor(() => expect(shown()).toBe(X))
    fireEvent.click(screen.getByText('to C'))
    await waitFor(() => expect(screen.getByTestId('conv').getAttribute('data-id')).toBe('conv-c'))
    await new Promise((r) => setTimeout(r, 50))
    expect(shown()).toBe('')
    expect(puts).toEqual([])
  })

  it('new-conversation-starts-without-a-document: the surface carries nothing from the open one', async () => {
    held['conv-a'] = X
    mount()
    await waitFor(() => expect(shown()).toBe(X))
    fireEvent.click(screen.getByTestId('agent-new-conversation-proj-test-claude'))
    await waitFor(() => expect(screen.getByTestId('new-conversation')).toBeInTheDocument())
    expect(window.location.search).not.toContain('document=')
  })
})
