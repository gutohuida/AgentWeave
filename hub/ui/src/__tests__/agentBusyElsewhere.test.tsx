import { render, screen, waitFor } from '@testing-library/react'
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
    useAgentTimeline: () => ({ data: { events: [], runs: {} } }),
  }
})

const other: AgentConversation = {
  id: 'conv-busy',
  agent: 'claude',
  provider_session_id: 'provider-busy',
  lifecycle: 'open', title: 'The one that is running', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-08-02T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
}

const conversation: AgentConversation = {
  id: 'conv-own',
  agent: 'claude',
  provider_session_id: 'provider-running',
  lifecycle: 'open', title: 'The second one', title_set_by_operator: false, origin: 'operator', attention: 'idle',
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
    runs: {},
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: [conversation, other] }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn(), isPending: false }),
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
  useQueueStatus: () => ({ data: { waiting_count: recordedEntries.length } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({
  useWorkspacePaths: () => ({ data: [] }),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [] }),
}))
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

const agentRunningElsewhere: AgentSummary = {
  name: 'claude',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
  running_conversation_id: 'conv-busy',
}

describe('a conversation whose agent is busy in another conversation (F844)', () => {
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

  it('offers no Stop and no "is responding", and names the conversation that is running', async () => {
    render(<AgentOutputPanel agent={agentRunningElsewhere} conversationId={conversation.id} />)

    await waitFor(() => expect(screen.getByRole('textbox')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /^stop/i })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).not.toHaveAttribute('placeholder', expect.stringContaining('is responding'))
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', expect.stringContaining('queue'))
    const busy = screen.getByTestId('conversation-busy-elsewhere')
    expect(busy).toHaveTextContent('The one that is running')
  })

  it('still offers Stop in the conversation the live run belongs to', async () => {
    render(<AgentOutputPanel agent={agentRunningElsewhere} conversationId={other.id} />)

    expect(await screen.findByRole('button', { name: /^stop/i })).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-busy-elsewhere')).not.toBeInTheDocument()
  })

  it('keeps the old reading when the roster does not name the conversation of the run', async () => {
    render(<AgentOutputPanel agent={{ ...agentRunningElsewhere, running_conversation_id: null }} conversationId={conversation.id} />)

    expect(await screen.findByRole('button', { name: /^stop/i })).toBeInTheDocument()
  })
})
