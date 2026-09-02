import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { useConfigStore } from '@/store/configStore'

let conversations: AgentConversation[] = []
let requestedConversationId: string | null = null

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

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return {
    ...actual,
    useAgentConversations: () => ({ data: conversations }),
    // Records what the panel actually asked for — the question section 8 exists to settle.
    useAgentChatHistory: (_agent: string | null, conversationId: string | null) => {
      requestedConversationId = conversationId
      return {
        data: { conversation_id: conversationId, session_id: null, agent: 'claude', entries: [] } as ChatHistoryResponse,
        isLoading: false,
      }
    },
    useAgentRecentChat: () => ({ data: undefined, isLoading: false }),
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
  useQueueStatus: () => ({ data: undefined }),
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

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

function conversation(id: string, title: string, overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id,
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title,
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-08T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
    ...overrides,
  }
}

describe('the panel renders the destination’s conversation, and holds no opinion of its own', () => {
  beforeEach(() => {
    requestedConversationId = null
    conversations = [
      conversation('conv-newest', 'The newest thread'),
      conversation('conv-older', 'An older thread'),
    ]
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('opens the conversation it is given, not the most recent one', async () => {
    // The defect section 8 exists to remove: the panel used to auto-select conversations[0]
    // and could clobber the conversation the operator activated in the rail.
    render(<AgentOutputPanel agent={agent} conversationId="conv-older" />)
    await waitFor(() => expect(requestedConversationId).toBe('conv-older'))
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('An older thread')
  })

  it('follows the destination when it changes', async () => {
    const { rerender } = render(<AgentOutputPanel agent={agent} conversationId="conv-older" />)
    await waitFor(() => expect(requestedConversationId).toBe('conv-older'))

    rerender(<AgentOutputPanel agent={agent} conversationId="conv-newest" />)
    await waitFor(() => expect(requestedConversationId).toBe('conv-newest'))
    expect(screen.getByTestId('session-continuity')).toHaveTextContent('The newest thread')
  })

  it('does not pick a conversation of its own when the destination names none', async () => {
    // The panel used to auto-select `conversations[0]` here. It no longer has an opinion:
    // resolving "which conversation" is the destination's job, and this is what the panel does
    // when the answer is "none".
    render(<AgentOutputPanel agent={agent} conversationId={null} />)
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'Next message starts a fresh conversation',
      ),
    )
    expect(requestedConversationId).toBeNull()
  })

  it('labels the open conversation by its title, never by its identifier', async () => {
    render(<AgentOutputPanel agent={agent} conversationId="conv-newest" />)
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent('The newest thread'),
    )
    expect(screen.getByTestId('session-continuity').textContent).not.toContain('conv-newest')
  })
})
