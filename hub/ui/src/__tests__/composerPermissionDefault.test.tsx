import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

/**
 * The composer's Permissions pill against an agent that has a default posture.
 *
 * The pill is the operator's statement of what the run will do. The Hub applies the agent's
 * default when the conversation states none, so a pill sitting at the catalog default while the
 * run went elsewhere would be the pill saying one thing and the run doing another — the same
 * failure `runner_commands` guards against on the other side of the wire.
 */

let roster: AgentSummary[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: [], isLoading: false }),
    useAgents: () => ({ data: roster }),
    useAgentLaunchability: () => ({ data: { agents: {} } }),
    useAgentTimeline: () => ({ data: [] }),
  }
})

const conversation: AgentConversation = {
  id: 'conv-posture',
  agent: 'claude',
  provider_session_id: 'provider-posture',
  lifecycle: 'open',
  title: 'A conversation',
  title_set_by_operator: false,
  origin: 'operator',
  attention: 'idle',
  created_at: '2026-08-08T10:00:00Z',
  updated_at: '2026-08-08T10:00:00Z',
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

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [{ id: 'runner-claude', cli: 'claude', model: 'claude-sonnet-5', name: 'Claude' }],
  }),
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

function agent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'claude',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    runner: 'claude',
    runner_id: 'runner-claude',
    ...overrides,
  }
}

const permissionsPill = () => screen.getByRole('button', { name: /^Permissions:/ })

describe("the composer shows the agent's default posture", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('reads the catalog default when the agent states none', () => {
    roster = [agent()]
    render(<AgentOutputPanel agent={roster[0]} conversationId={conversation.id} />)
    expect(permissionsPill()).toHaveTextContent('Edit files')
  })

  it("reads the agent's default when it has one", () => {
    roster = [agent({ default_permission_mode: 'manual' })]
    render(<AgentOutputPanel agent={roster[0]} conversationId={conversation.id} />)
    expect(permissionsPill()).toHaveTextContent('Ask me')
  })

  it('does not turn the default into a choice made for this conversation', async () => {
    // Showing it is not the same as sending it. The Hub applies the default itself, so sending it
    // back would silently freeze today's default onto this conversation the first time the
    // operator typed anything — and then changing the agent's default would leave it behind.
    roster = [agent({ default_permission_mode: 'manual' })]
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'started', conversation_id: conversation.id }), {
        status: 200,
      }),
    )
    render(<AgentOutputPanel agent={roster[0]} conversationId={conversation.id} />)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'go' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body.overrides).toBeUndefined()
  })
})
