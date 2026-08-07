import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentOutputLine, AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

let outputLines: AgentOutputLine[] = []
let conversations: AgentConversation[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: outputLines, isLoading: false }),
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
}))

vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/queue', () => ({
  useQueueStatus: () => ({ data: undefined }),
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

const agent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

function triggerBody(callIndex: number): Record<string, unknown> {
  return JSON.parse(fetchMock.mock.calls[callIndex][1].body as string)
}

describe('agent conversation handoff', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [{
      id: 'conv-old',
      agent: 'claude',
      provider_session_id: 'session-old',
      lifecycle: 'open',
      created_at: '2026-07-29T11:00:00Z',
      updated_at: '2026-07-29T12:00:00Z',
    }]
    fetchMock.mockReset()
    fetchMock.mockImplementation((_url, init) => {
      const body = JSON.parse(init.body as string) as { conversation_id?: string }
      return Promise.resolve(new Response(JSON.stringify({
        status: 'running',
        conversation_id: body.conversation_id ?? 'conv-new',
      }), { status: 200 }))
    })
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('checkpoints the old session and resumes the handoff in exactly one new session', async () => {
    const onConversationChange = vi.fn()
    const user = userEvent.setup()
    const view = render(<AgentOutputPanel agent={agent} onConversationChange={onConversationChange} />)
    expect(screen.getAllByTestId('conversation-header')).toHaveLength(1)

    await waitFor(() => expect(onConversationChange).toHaveBeenCalledWith('conv-old'))

    await user.click(screen.getByLabelText('Conversation actions'))
    await user.click(await screen.findByRole('menuitem', { name: /Handoff/ }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(triggerBody(0)).toMatchObject({
      agent: 'claude',
      conversation_id: 'conv-old',
    })
    expect(triggerBody(0).message).toContain('aw-checkpoint skill')
    await waitFor(() => expect(onConversationChange).toHaveBeenCalledWith(null))
    expect(screen.getByTestId('session-continuity')).toHaveTextContent(
      'Preparing durable handoff',
    )

    outputLines = [
      {
        id: 'handoff-complete',
        agent: 'claude',
        session_id: 'session-old',
        content: 'Completed',
        timestamp: '2026-07-29T12:00:00Z',
        kind: 'status',
        payload: { phase: 'completed' },
      },
    ]
    view.rerender(<AgentOutputPanel agent={agent} onConversationChange={onConversationChange} />)

    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent('Handoff ready'),
    )

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Continue implementing the feature.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(triggerBody(1)).toMatchObject({
      agent: 'claude',
    })
    expect(triggerBody(1)).not.toHaveProperty('conversation_id')
    expect(triggerBody(1).message).toContain('Resume from the latest durable AgentWeave handoff')
    expect(triggerBody(1).message).toContain('Continue implementing the feature.')

    outputLines = [
      ...outputLines,
      {
        id: 'new-session-started',
        agent: 'claude',
        session_id: 'session-new',
        content: 'Started',
        timestamp: '2026-07-29T12:01:00Z',
        kind: 'status',
        payload: { phase: 'started' },
      },
    ]
    await waitFor(() => expect(onConversationChange).toHaveBeenCalledWith('conv-new'))

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'And now continue normally.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(triggerBody(2)).toEqual({
      agent: 'claude',
      message: 'And now continue normally.',
      conversation_id: 'conv-new',
    })
  })
})
