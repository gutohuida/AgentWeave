import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse, TimelineEntry } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

let recordedEntries: TimelineEntry[] = []

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
  id: 'conv-running',
  agent: 'claude',
  provider_session_id: 'provider-running',
  lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-08-02T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
}

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversation.id,
    session_id: conversation.provider_session_id,
    agent: conversation.agent,
    entries: recordedEntries,
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: [conversation] }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/unaskedQuestions', () => ({
  usePendingUnaskedQuestions: () => ({ data: [] }),
  useResolveUnaskedQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  // The mutations stay real — they go through the mocked fetch, which is what these assert on.
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: recordedEntries.length } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({
  useWorkspacePaths: () => ({ data: [] }),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [] }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const runningAgent: AgentSummary = {
  name: 'claude',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

const idleAgent: AgentSummary = { ...runningAgent, status: 'idle' }

function queuedEntry(id: string, content: string, sequence: number): TimelineEntry {
  return {
    id,
    kind: 'operator_input',
    content,
    timestamp: `2026-08-02T10:00:0${sequence}Z`,
    delivery_state: 'queued',
    sequence,
    hop_depth: 0,
  }
}

function triggerBody(callIndex: number): Record<string, unknown> {
  return JSON.parse(fetchMock.mock.calls[callIndex][1].body as string)
}

describe('running-agent composer', () => {
  beforeEach(() => {
    recordedEntries = []
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('submits two messages while running and renders only recorded queued entries in order', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'queued',
        conversation_id: conversation.id,
        queue_entry_id: 'entry-1',
        waiting_reason: 'agent is already running',
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        status: 'queued',
        conversation_id: conversation.id,
        queue_entry_id: 'entry-2',
        waiting_reason: 'agent is already running',
      }), { status: 200 }))

    const view = render(<AgentOutputPanel agent={runningAgent} conversationId={conversation.id} />)
    const composer = screen.getByRole('textbox')
    const send = screen.getByRole('button', { name: 'Send message' })

    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(conversation.title as string),
    )
    expect(composer).toBeEnabled()

    fireEvent.change(composer, { target: { value: 'First follow-up' } })
    expect(send).toBeEnabled()
    fireEvent.click(send)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(composer).toHaveValue(''))
    expect(triggerBody(0)).toEqual({
      agent: 'claude',
      message: 'First follow-up',
      conversation_id: conversation.id,
    })
    expect(screen.queryByText('First follow-up')).not.toBeInTheDocument()

    recordedEntries = [queuedEntry('entry-1', 'First follow-up', 1)]
    view.rerender(<AgentOutputPanel agent={runningAgent} conversationId={conversation.id} />)
    expect(await screen.findByText('First follow-up')).toBeInTheDocument()
    expect(screen.getAllByText('queued')).toHaveLength(1)

    fireEvent.change(composer, { target: { value: 'Second follow-up' } })
    fireEvent.click(send)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(triggerBody(1)).toEqual({
      agent: 'claude',
      message: 'Second follow-up',
      conversation_id: conversation.id,
    })

    recordedEntries = [
      queuedEntry('entry-1', 'First follow-up', 1),
      queuedEntry('entry-2', 'Second follow-up', 2),
    ]
    view.rerender(<AgentOutputPanel agent={runningAgent} conversationId={conversation.id} />)

    const first = await screen.findByText('First follow-up')
    const second = await screen.findByText('Second follow-up')
    expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getAllByText('queued')).toHaveLength(2)
  })

  it('clears text during submission and restores it when the trigger fails', async () => {
    let finishRequest: (response: Response) => void = () => undefined
    fetchMock.mockReturnValueOnce(new Promise<Response>((resolve) => {
      finishRequest = resolve
    }))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(<AgentOutputPanel agent={idleAgent} conversationId={conversation.id} />)
    const composer = screen.getByRole('textbox')
    fireEvent.change(composer, { target: { value: 'Please preserve this draft' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(composer).toHaveValue('')
    expect(composer).toBeDisabled()

    finishRequest(new Response('failed', { status: 503 }))

    await waitFor(() => expect(composer).toHaveValue('Please preserve this draft'))
    expect(composer).toBeEnabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to send message')
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('Failed to send message')
    errorSpy.mockRestore()
  })
})
