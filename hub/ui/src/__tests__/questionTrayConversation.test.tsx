import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import type { Question } from '@/api/questions'
import { useConfigStore } from '@/store/configStore'
import { activeQuestionFor } from '@/lib/pendingQuestions'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

/** The batch the panel is holding, newest state per test. */
let openQuestions: Question[] = []
const answerMutation = vi.fn().mockResolvedValue({})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: [], isLoading: false }),
    useAgents: () => ({ data: [] }),
    useAgentLaunchability: () => ({ data: { agents: {} } }),
    useAgentTimeline: () => ({ data: { events: [], runs: {} } }),
  }
})

const conversation: AgentConversation = {
  id: 'conv-1',
  agent: 'codex-1',
  provider_session_id: 'provider-1',
  lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-08-07T10:00:00Z',
  updated_at: '2026-08-07T10:00:00Z',
}

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversation.id,
    session_id: conversation.provider_session_id,
    agent: conversation.agent,
    entries: [],
    runs: {},
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: [conversation] }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: openQuestions }),
  useAnswerQuestion: () => ({ mutateAsync: answerMutation, isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissPermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  // The mutations stay real — they go through the mocked fetch, which is what these assert on.
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/accounting', () => ({
  useAccounting: () => ({ data: undefined }),
  useConversationAccounting: () => ({ data: undefined }),
}))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const agent: AgentSummary = {
  name: 'codex-1',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'codex',
}

function asked(overrides: Partial<Question>): Question {
  return {
    id: 'q-stale',
    project_id: 'proj-test',
    from_agent: 'codex-1',
    question: 'Which name should the helper have?',
    blocking: true,
    options: [
      { label: 'double', description: 'first' },
      { label: 'twice', description: 'second' },
    ],
    multi_select: false,
    answered: false,
    created_by_run_id: 'run-1',
    created_at: '2026-10-20T10:00:00Z',
    ...overrides,
  }
}

// F804: the tray in one conversation carried a question asked in another, and the composer routed
// every typed message to it as the answer, whether or not anyone still waited.
describe('a question belongs to the conversation it was asked in', () => {
  it('leaves a question asked in another conversation out of this conversation’s tray', () => {
    const rows = [asked({ conversation_id: 'conv-A' })]
    expect(activeQuestionFor(rows, 'codex-1', 'conv-B').question).toBeNull()
    expect(activeQuestionFor(rows, 'codex-1', 'conv-A').question?.id).toBe('q-stale')
  })

  it('keeps a question that names no conversation visible everywhere, as before', () => {
    const rows = [asked({ conversation_id: null }), asked({ id: 'q-old-hub' })]
    expect(activeQuestionFor(rows, 'codex-1', 'conv-B').question).not.toBeNull()
    expect(activeQuestionFor(rows, 'codex-1', null).question).not.toBeNull()
  })

  it('shows a question asked in a conversation nowhere on the new-conversation surface', () => {
    const rows = [asked({ conversation_id: 'conv-A' })]
    expect(activeQuestionFor(rows, 'codex-1', null).question).toBeNull()
  })
})

describe('the composer and a question nobody waits on', () => {
  beforeEach(() => {
    openQuestions = []
    answerMutation.mockClear()
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ status: 'queued', conversation_id: 'conv-1', queue_entry_id: 'e-1' }),
        { status: 200 },
      ),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_test',
      isConfigured: true,
      selectedProjectId: 'proj-test',
    })
  })

  it('does not put another conversation’s question over this composer', () => {
    openQuestions = [asked({ conversation_id: 'conv-A', asker_waiting: false })]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
    expect(screen.queryByText('Which name should the helper have?')).not.toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Answer codex-1…')).not.toBeInTheDocument()
  })

  it('sends typed text as a message when the question in this conversation is no longer waited on', async () => {
    openQuestions = [asked({ conversation_id: 'conv-1', asker_waiting: false })]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    const composer = screen.getByPlaceholderText(/^Answer codex-1/)
    fireEvent.change(composer, { target: { value: 'New task: add subtract()' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    expect(fetchMock.mock.calls[0][0]).toContain('/agent/trigger')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({
      message: 'New task: add subtract()',
    })
    expect(answerMutation).not.toHaveBeenCalled()
  })

  it('still answers it when an option is picked', async () => {
    openQuestions = [asked({ conversation_id: 'conv-1', asker_waiting: false })]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
    fireEvent.click(screen.getByTestId('agent-question-option-q-stale-0'))
    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-stale', answer: 'double' })
  })

  it('still routes typed text to a question that is waited on', async () => {
    openQuestions = [asked({ conversation_id: 'conv-1', asker_waiting: true })]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
    const composer = screen.getByPlaceholderText(/^Answer codex-1/)
    fireEvent.change(composer, { target: { value: 'triple' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-stale', answer: 'triple' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
