import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import type { Question } from '@/api/questions'
import { useConfigStore } from '@/store/configStore'
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
    useAgentTimeline: () => ({ data: [] }),
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

;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi.fn()

const agent: AgentSummary = {
  name: 'codex-1',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'codex',
}

function batched(index: number, total: number, answered = false): Question {
  return {
    id: `q-${index + 1}`,
    project_id: 'proj-test',
    from_agent: 'codex-1',
    question: `Question ${index + 1}?`,
    blocking: true,
    options: [
      { label: `A${index + 1}`, description: 'first' },
      { label: `B${index + 1}`, description: 'second' },
    ],
    header: 'Decide',
    multi_select: false,
    answered,
    batch_id: 'qbatch-1',
    batch_index: index,
    batch_size: total,
    created_at: `2026-08-07T10:0${index}:00Z`,
  }
}

describe('answering a batch through the composer', () => {
  beforeEach(() => {
    openQuestions = []
    answerMutation.mockClear()
    useConfigStore.setState({
      apiKey: 'aw_live_test',
      isConfigured: true,
      selectedProjectId: 'proj-test',
    })
  })

  it('records the answer against the question actually on screen', async () => {
    // Handed to the panel out of order on purpose: the card and the composer derive the active
    // question independently-looking code paths, and if they disagreed the operator would read
    // one question while answering another. Nothing on screen would show it.
    openQuestions = [batched(2, 3), batched(0, 3), batched(1, 3)]
    render(<AgentOutputPanel agent={agent} />)

    expect(screen.getByText('Question 1?')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('agent-question-option-q-1-0'))

    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-1', answer: 'A1' })
  })

  it('advances to the next question once the first is answered', async () => {
    openQuestions = [batched(0, 3), batched(1, 3), batched(2, 3)]
    const { rerender } = render(<AgentOutputPanel agent={agent} />)
    expect(screen.getByTestId('agent-question-count')).toHaveTextContent('1/3')

    openQuestions = [batched(0, 3, true), batched(1, 3), batched(2, 3)]
    rerender(<AgentOutputPanel agent={agent} />)

    expect(screen.getByText('Question 2?')).toBeInTheDocument()
    expect(screen.getByTestId('agent-question-count')).toHaveTextContent('2/3')

    fireEvent.click(screen.getByTestId('agent-question-option-q-2-1'))
    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({ id: 'q-2', answer: 'B2' })
  })

  it('sends a single-choice answer from the click that chose it', async () => {
    // Regression: the click handler set the selection with setQuestionSelection and then called
    // the submit path in the same tick, which read that state from a closure it had not updated
    // yet — so it saw no selection and returned without sending anything. Clicking an option did
    // nothing at all, and the agent went on waiting.
    openQuestions = [
      { ...batched(0, 1), batch_id: null, batch_index: 0, batch_size: 1, multi_select: false },
    ]
    render(<AgentOutputPanel agent={agent} />)

    fireEvent.click(screen.getByTestId('agent-question-option-q-1-0'))

    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({
      id: 'q-1',
      answer: 'A1',
      labels: ['A1'],
    })
  })

  it('keeps the composer pointed at the active question for a typed answer', async () => {
    openQuestions = [batched(0, 2, true), batched(1, 2)]
    render(<AgentOutputPanel agent={agent} />)

    const composer = screen.getByPlaceholderText('Answer codex-1…')
    fireEvent.change(composer, { target: { value: 'neither, use C' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => expect(answerMutation).toHaveBeenCalled())
    expect(answerMutation.mock.calls[0][0]).toMatchObject({
      id: 'q-2',
      answer: 'neither, use C',
    })
  })
})
