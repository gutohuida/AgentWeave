import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { loadAllScreens } from '@/lib/lazyScreens'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { setComposerText } from './testUtils/composerField'

/** Starting a thread from the new-thread composer lands the operator in that thread: the first
 *  message creates the conversation, and the main view follows it rather than staying on an empty
 *  composer while the thread only appears in the rail. */

vi.mock('@/api/reopeningWarnings', () => ({
  useReopeningWarnings: () => ({ data: [], error: null }),
  useStopReopenedBuild: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissReopeningWarning: () => ({ mutate: vi.fn(), isPending: false }),
}))
// The listeners the app registered, so a test can play the Hub's stream.
const sse = vi.hoisted(() => ({ listeners: new Set<(event: { type: string; data: unknown }) => void>() }))
vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: (listener?: (event: { type: string; data: unknown }) => void) => {
    if (listener) sse.listeners.add(listener)
  },
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const triggers: unknown[] = []
// When set, the trigger answers only once this is called: the Hub starting the turn can take a
// while (it prepares the agent's checkout first) and answers when it is done.
let releaseTrigger: (() => void) | null = null
let holdTrigger = false
vi.stubGlobal(
  'fetch',
  vi.fn(async (url: string, init?: RequestInit) => {
    const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) }) as unknown as Response
    if (String(url).endsWith('/agent/trigger')) {
      triggers.push(JSON.parse(String(init?.body)))
      if (holdTrigger) await new Promise<void>((resolve) => { releaseTrigger = resolve })
      // The route's own shape (TriggerAgentResponse): a fresh conversation's id rides with it.
      return json({
        success: true, message: 'claude started (run run-1).', agent: 'claude', run_id: 'run-1',
        status: 'running', conversation_id: 'conv-fresh',
      })
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
      agents: [{ id: 'agent-claude', name: 'claude', color_index: 2, status: 'idle', last_seen: null }],
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
    data: [{ name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2 }],
    isLoading: false,
  }),
}))
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({ data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }),
  useSpecEvents: () => {},
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: undefined }),
}))
vi.mock('@/components/layout/SetupModal', () => ({ SetupModal: () => null }))
// The conversation view, reduced to the conversation it was handed.
vi.mock('@/components/agents/ConversationView', () => ({
  ConversationView: (props: { conversationId: string | null }) => (
    <div data-testid="conv" data-id={props.conversationId ?? ''} />
  ),
}))

import App from '@/App'

beforeAll(() => loadAllScreens(), 90000)

describe('the new-thread composer', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    triggers.length = 0
    holdTrigger = false
    releaseTrigger = null
    sse.listeners.clear()
    window.history.pushState(null, '', '?project=proj-test&agent=claude&conversation=__new__')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-test',
      isConfigured: true, bootstrapState: 'ready', mode: 'light',
    })
  })

  it('takes the operator to the thread its first message created', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>)

    await waitFor(() => expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument())
    setComposerText(screen.getByRole('textbox'), 'Start something')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(triggers).toHaveLength(1))
    await waitFor(() => expect(screen.getByTestId('conv')).toHaveAttribute('data-id', 'conv-fresh'))
    expect(window.location.search).toContain('conversation=conv-fresh')
    expect(screen.queryByTestId('new-conversation-surface')).not.toBeInTheDocument()
  })

  it('does too when it was opened from the rail with no profile and one was chosen there', async () => {
    window.history.pushState(null, '', '?project=proj-test&conversation=__new__')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>)

    await waitFor(() => expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument())
    fireEvent.click(await screen.findByTestId('new-conversation-agent-claude'))
    await waitFor(() => expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent('claude'))
    setComposerText(screen.getByRole('textbox'), 'Start something')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(triggers).toHaveLength(1))
    await waitFor(() => expect(screen.getByTestId('conv')).toHaveAttribute('data-id', 'conv-fresh'))
    expect(window.location.search).toContain('conversation=conv-fresh')
  })

  it('does not wait for the Hub to finish starting the turn: the thread is announced first', async () => {
    holdTrigger = true
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>)

    await waitFor(() => expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument())
    setComposerText(screen.getByRole('textbox'), 'Start something')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(triggers).toHaveLength(1))

    // The route commits the entry and broadcasts it before it tries to start the turn
    // (agent_trigger.py: `persist_accepted_event` / `queue_entry_queued`, then `schedule_accepted`).
    sse.listeners.forEach((listener) =>
      listener({
        type: 'queue_entry_queued',
        data: {
          project_id: 'proj-test', entry_id: 'e1', agent: 'claude',
          conversation_id: 'conv-fresh', origin_type: 'operator', hop_depth: 0,
        },
      }),
    )
    await waitFor(() => expect(screen.getByTestId('conv')).toHaveAttribute('data-id', 'conv-fresh'))
    expect(window.location.search).toContain('conversation=conv-fresh')

    // The late answer adds no second step to the history.
    const before = window.history.length
    releaseTrigger?.()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(window.history.length).toBe(before)
  })

  it('ignores another agent’s queued input while it waits', async () => {
    holdTrigger = true
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><App /></QueryClientProvider>)

    await waitFor(() => expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument())
    setComposerText(screen.getByRole('textbox'), 'Start something')
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(triggers).toHaveLength(1))

    sse.listeners.forEach((listener) =>
      listener({
        type: 'queue_entry_queued',
        data: { project_id: 'proj-test', agent: 'codex', conversation_id: 'conv-other', origin_type: 'operator' },
      }),
    )
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument()
    releaseTrigger?.()
    await waitFor(() => expect(screen.getByTestId('conv')).toHaveAttribute('data-id', 'conv-fresh'))
  })
})
