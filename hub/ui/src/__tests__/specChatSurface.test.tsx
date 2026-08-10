import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import type { PermissionRequest } from '@/api/permissions'
import type { Question } from '@/api/questions'
import { useConfigStore } from '@/store/configStore'
import { SpecChat } from '@/components/spec/SpecChat'

/* The specification workspace's chat is the one conversation surface.
 *
 * The surface this replaced (`SpecChatPane`) could not render a permission card, a question
 * card, or a checkpoint banner — searching it for `permission|question|checkpoint|Banner`
 * returned nothing — so an agent that asked the operator anything from the Spec page blocked
 * with nothing shown. That is the defect this change exists to fix, so it is demonstrated here
 * rather than asserted: these tests render the real `SpecChat`, mounting the real
 * `AgentOutputPanel`, `Composer`, `PermissionRequestCard` and `AgentQuestionCard`.
 */

let conversations: AgentConversation[] = []
let openQuestions: Question[] = []
let permissionRequests: PermissionRequest[] = []
const answerMutation = vi.fn().mockResolvedValue({})
const decide = vi.fn()

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: [], isLoading: false }),
    useAgents: () => ({ data: [] }),
    useAgentLaunchability: () => ({ data: { agents: {} } }),
    useAgentTimeline: () => ({ data: [] }),
  }
})

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversations[0]?.id ?? null,
    session_id: null,
    agent: 'speccer',
    entries: [],
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: conversations }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: openQuestions }),
  useAnswerQuestion: () => ({ mutateAsync: answerMutation, isPending: false }),
}))

vi.mock('@/api/permissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/permissions')>()),
  usePendingPermissionRequests: () => ({ data: permissionRequests }),
  useDecidePermissionRequest: () => ({ mutate: decide, isPending: false }),
}))

vi.mock('@/api/unaskedQuestions', () => ({
  usePendingUnaskedQuestions: () => ({ data: [] }),
  useResolveUnaskedQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const AGENTS: AgentSummary[] = [
  { name: 'speccer', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' },
  { name: 'other', status: 'idle', message_count: 0, active_task_count: 0, runner: 'codex' },
]

function conversation(overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id: 'conv-1',
    agent: 'speccer',
    provider_session_id: null,
    lifecycle: 'open',
    title: 'Reviewing the baseline',
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-10T10:00:00Z',
    updated_at: '2026-08-10T10:00:00Z',
    ...overrides,
  }
}

function renderChat(documentPath: string | null = 'spec/a1-probe.html') {
  const onSelectedAgentChange = vi.fn()
  const utils = render(
    <SpecChat
      agents={AGENTS}
      selectedAgent="speccer"
      onSelectedAgentChange={onSelectedAgentChange}
      documentPath={documentPath}
    />
  )
  return { ...utils, onSelectedAgentChange }
}

/** The JSON body of the Nth /agent/trigger call. */
function triggerBody(call = 0): Record<string, unknown> {
  const [path, init] = fetchMock.mock.calls[call] as [string, RequestInit]
  expect(path).toBe('/api/v1/projects/proj-test/agent/trigger')
  return JSON.parse(init.body as string)
}

async function send(text: string) {
  const textarea = screen.getByRole('textbox')
  fireEvent.change(textarea, { target: { value: text } })
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
}

beforeEach(() => {
  cleanup()
  conversations = []
  openQuestions = []
  permissionRequests = []
  answerMutation.mockClear()
  decide.mockClear()
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: 'running', conversation_id: 'conv-new' }),
  })
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
    mode: 'light',
  })
})

describe('the specification workspace mounts the one composer', () => {
  it('renders the shared composer rather than a second message input', () => {
    renderChat()
    expect(screen.getByTestId('conversation-output')).toBeInTheDocument()
    expect(screen.getByTestId('conversation-header')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('creates a conversation with the first message when the agent has none', async () => {
    renderChat()
    expect(screen.getByTestId('session-continuity')).toHaveTextContent(
      'Next message starts a fresh conversation'
    )

    await send('what does this document say?')

    const body = triggerBody()
    expect(body.agent).toBe('speccer')
    expect(body.message).toBe('what does this document say?')
    // `conversationId: null` — the Hub creates one from the message (design.md Decision 1).
    expect(body.conversation_id).toBeUndefined()
    // No specification-scoped origin is produced. Nothing in the request names one.
    expect(JSON.stringify(body)).not.toContain('origin')
  })

  it('continues the agent’s own most recent conversation when it has one', () => {
    conversations = [
      conversation({ id: 'conv-old', updated_at: '2026-08-09T10:00:00Z', title: 'Older' }),
      conversation({ id: 'conv-new', updated_at: '2026-08-10T12:00:00Z', title: 'Newest' }),
    ]
    renderChat()
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('Continuing Newest')
  })

  it('ignores an archived conversation when choosing which one is on screen', () => {
    conversations = [
      conversation({ id: 'conv-archived', updated_at: '2026-08-10T18:00:00Z', lifecycle: 'archived' }),
      conversation({ id: 'conv-open', updated_at: '2026-08-10T09:00:00Z', title: 'Still open' }),
    ]
    renderChat()
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('Continuing Still open')
  })
})

describe('the open document travels as context, not as the message', () => {
  it('sends the document the operator is viewing alongside their message', async () => {
    renderChat('spec/a1-probe.html')
    await send('why does this say that?')

    const body = triggerBody()
    expect(body.spec_document).toBe('spec/a1-probe.html')
    // The message is the durable record of what the operator said.
    expect(body.message).toBe('why does this say that?')
  })

  it('sends no document when none is open, rather than an empty one', async () => {
    renderChat(null)
    await send('hello')
    expect(triggerBody().spec_document).toBeUndefined()
  })
})

describe('the operator can be involved from the specification workspace', () => {
  it('renders a question the agent asked, and answers it', async () => {
    openQuestions = [
      {
        id: 'q-1',
        project_id: 'proj-test',
        from_agent: 'speccer',
        question: 'Should the baseline keep the old glossary?',
        blocking: true,
        options: [
          { label: 'Keep it', description: 'Nothing else references it yet' },
          { label: 'Drop it', description: 'It has been wrong since July' },
        ],
        header: 'Glossary',
        multi_select: false,
        answered: false,
        created_at: '2026-08-10T10:00:00Z',
      } as Question,
    ]
    renderChat()

    expect(screen.getByText('Should the baseline keep the old glossary?')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Drop it'))
    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-1', labels: ['Drop it'] })
    // The answer went to the question, not out as a new message.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('renders a permission request and resolves it both ways', () => {
    permissionRequests = [
      {
        id: 'perm-1',
        agent: 'speccer',
        run_id: 'run-1',
        tool_name: 'Write',
        tool_use_id: 'toolu_1',
        tool_input: { file_path: 'spec/a1-probe.html', content: 'x' },
        status: 'pending',
        created_at: '2026-08-10T10:00:00Z',
        decided_at: null,
        decided_by: null,
      },
    ]
    renderChat()

    expect(screen.getByText(/speccer wants to use Write/)).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('permission-allow-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: true })
    fireEvent.click(screen.getByTestId('permission-deny-perm-1'))
    expect(decide).toHaveBeenCalledWith({ id: 'perm-1', allow: false })
  })

  it('does not show another agent’s permission request', () => {
    permissionRequests = [
      {
        id: 'perm-2',
        agent: 'other',
        run_id: 'run-2',
        tool_name: 'Bash',
        tool_use_id: 'toolu_2',
        tool_input: { command: 'rm -rf /' },
        status: 'pending',
        created_at: '2026-08-10T10:00:00Z',
        decided_at: null,
        decided_by: null,
      },
    ]
    renderChat()
    expect(screen.queryByTestId('permission-request-perm-2')).not.toBeInTheDocument()
  })
})

describe('picking which agent the operator is talking to', () => {
  it('offers the roster when there is more than one agent', () => {
    const { onSelectedAgentChange } = renderChat()
    fireEvent.change(screen.getByLabelText('Agent'), { target: { value: 'other' } })
    expect(onSelectedAgentChange).toHaveBeenCalledWith('other')
  })

  it('offers no picker when there is only one agent to pick', () => {
    render(
      <SpecChat
        agents={[AGENTS[0]]}
        selectedAgent="speccer"
        onSelectedAgentChange={vi.fn()}
        documentPath={null}
      />
    )
    expect(screen.queryByLabelText('Agent')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('says so when the project has no agent at all', () => {
    render(
      <SpecChat
        agents={[]}
        selectedAgent=""
        onSelectedAgentChange={vi.fn()}
        documentPath={null}
      />
    )
    expect(screen.getByText('No agent')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
