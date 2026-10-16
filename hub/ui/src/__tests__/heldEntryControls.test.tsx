import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'

import { ControlledConversation } from './support/ControlledConversation'

/**
 * F131 — the Continue control said "Continuing…" for a turn that began somewhere else.
 *
 * The turn is the agent's, and the Hub builds it from the oldest eligible input across the whole
 * queue, so the conversation that starts is frequently not the one the operator pressed. The
 * button's own gate cannot prevent this: it reads client-side state in which another
 * conversation's older entry does not appear. These three cases are keyed on what the server
 * answered, never on rendering timing.
 */

let conversations: AgentConversation[] = []
let chatEntries: unknown[] = []

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
    useAgentChatHistory: () => ({ data: { entries: chatEntries, runs: {} }, isLoading: false }),
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
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

// The button renders because an undelivered entry names the conversation on screen — exactly the
// gate the shipped UI applies. The point of these tests is that the gate being satisfied is not
// the same as this conversation being the one that starts.
vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({
    data: [{ id: 'held-1', conversation_id: 'conv-watched', agent: 'claude' }],
  }),
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

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

function conversation(id: string, title: string): AgentConversation {
  return {
    id,
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title,
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-30T01:00:00Z',
    updated_at: '2026-08-30T01:00:00Z',
  }
}

/** F653: one hop-held entry drew three Continue controls and two explanations, one of them a red
 *  error band. The entry's own Continue and Discard, and the amber note above it, are enough. */
describe('a hop-held entry in the conversation (F653)', () => {
  beforeEach(() => {
    conversations = [conversation('conv-watched', 'The one on screen')]
    chatEntries = [
      {
        id: 'held-1',
        kind: 'inbound_peer',
        participant: 'codex',
        content: 'over budget',
        timestamp: '2026-08-30T01:00:00Z',
        delivery_state: 'queued',
        hop_budget_exceeded: true,
        conversation_id: 'conv-watched',
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

  it('offers one Continue, on the entry, and no red error band', async () => {
    render(<ControlledConversation agent={agent} conversationId="conv-watched" />)
    expect(await screen.findByText('Autonomous continuation paused')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Continue$/ })).toHaveLength(1)
    expect(screen.queryByTestId('conversation-continue')).toBeNull()
    expect(screen.queryByText(/reached the hop limit and will not be delivered/)).toBeNull()
  })
})
