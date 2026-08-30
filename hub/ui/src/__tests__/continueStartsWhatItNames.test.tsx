import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  return {
    ...actual,
    useAgentConversations: () => ({ data: conversations }),
    useAgentChatHistory: () => ({ data: undefined, isLoading: false }),
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
    data: [{ id: 'entry-mine', conversation_id: 'conv-watched', agent: 'claude' }],
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

function answerContinueWith(body: Record<string, unknown>) {
  fetchMock.mockImplementation((url) => {
    if (String(url).endsWith('/continue')) {
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    }
    return Promise.resolve(new Response('{}', { status: 200 }))
  })
}

async function pressContinue() {
  const user = userEvent.setup()
  render(<ControlledConversation agent={agent} conversationId="conv-watched" />)
  await user.click(await screen.findByTestId('conversation-continue'))
}

describe('the Continue control reports the turn that actually began', () => {
  beforeEach(() => {
    conversations = [
      conversation('conv-watched', 'The one on screen'),
      conversation('conv-elsewhere', 'Somebody else’s thread'),
    ]
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('confirms continuing when this conversation is the one that started', async () => {
    answerContinueWith({
      agent: 'claude',
      conversation_id: 'conv-watched',
      started: true,
      started_conversation_id: 'conv-watched',
      waiting_reason: null,
    })

    await pressContinue()

    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent('Continuing…'),
    )
  })

  it('states the wait and names the conversation that began instead', async () => {
    answerContinueWith({
      agent: 'claude',
      conversation_id: 'conv-watched',
      started: false,
      started_conversation_id: 'conv-elsewhere',
      waiting_reason: "this conversation's input is waiting behind other input",
    })

    await pressContinue()

    await waitFor(() => {
      const notice = screen.getByTestId('session-continuity')
      // The server's own reason, rendered rather than restated — it already distinguishes
      // waiting-behind-input from nothing-queued, and composing that judgement a second time
      // client-side is how the two answers drift apart.
      expect(notice).toHaveTextContent('waiting behind other input')
      // By label, never by identifier.
      expect(notice).toHaveTextContent('Somebody else’s thread started instead.')
      expect(notice).not.toHaveTextContent('conv-elsewhere')
    })
  })

  it('states the reason and names nothing when no turn began', async () => {
    answerContinueWith({
      agent: 'claude',
      conversation_id: 'conv-watched',
      started: false,
      started_conversation_id: null,
      waiting_reason: 'agent is already running',
    })

    await pressContinue()

    await waitFor(() => {
      const notice = screen.getByTestId('session-continuity')
      expect(notice).toHaveTextContent('Not started — agent is already running')
      expect(notice).not.toHaveTextContent('started instead')
    })
  })
})
