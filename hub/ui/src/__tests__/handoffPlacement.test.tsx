import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { useConfigStore } from '@/store/configStore'

let conversations: AgentConversation[] = []

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
    agent: 'claude',
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
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutate: vi.fn(), isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissPermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
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

const idleAgent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}
const manualAgent: AgentSummary = { ...idleAgent, runner: 'manual' }
const runningAgent: AgentSummary = { ...idleAgent, status: 'running' }

describe('durable handoff has a persistent place on the conversation', () => {
  beforeEach(() => {
    cleanup()
    conversations = [
      {
        id: 'conv-old',
        agent: 'claude',
        provider_session_id: null,
        lifecycle: 'open',
        title: 'A conversation',
        title_set_by_operator: false,
        origin: 'operator',
        attention: 'idle',
        created_at: '2026-08-08T00:00:00Z',
        updated_at: '2026-08-08T00:00:00Z',
      },
    ]
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('is labelled and visible on the header at rest, not behind a menu', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const handoff = await screen.findByTestId('conversation-handoff')

    expect(handoff).toHaveTextContent('Checkpoint')
    expect(handoff).toBeEnabled()
    // On the header, beside "Fold all turns" — the operator's requirement was an explicit place
    // they can see, because "users might not know or forget about the handoff".
    expect(screen.getByTestId('conversation-header')).toContainElement(handoff)
    const foldAll = screen.getByRole('button', { name: 'Fold all turns' })
    expect(screen.getByTestId('conversation-header')).toContainElement(foldAll)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('states its reason when the runner cannot manage a session', async () => {
    render(<AgentOutputPanel agent={manualAgent} conversationId="conv-old" />)
    const handoff = await screen.findByTestId('conversation-handoff')

    // Present and disabled, not omitted — the control set must not shift between agents.
    expect(handoff).toBeDisabled()
    expect(handoff).toHaveAccessibleName('Checkpoint — Requires an automatically managed runner')
  })

  it('states its reason when no conversation is open', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId={null} />)
    const handoff = await screen.findByTestId('conversation-handoff')

    expect(handoff).toBeDisabled()
    expect(handoff).toHaveAccessibleName('Checkpoint — Start a conversation first')
  })

  it('states its reason while the agent is busy', async () => {
    render(<AgentOutputPanel agent={runningAgent} conversationId="conv-old" />)
    const handoff = await screen.findByTestId('conversation-handoff')

    await waitFor(() => expect(handoff).toBeDisabled())
    expect(handoff).toHaveAccessibleName('Checkpoint — Unavailable while the agent is busy')
  })
})
