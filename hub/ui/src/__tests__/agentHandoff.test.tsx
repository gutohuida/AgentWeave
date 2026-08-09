import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentOutputLine, AgentSummary } from '@/api/agents'
import type { AgentConversation } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'

import { ControlledConversation } from './support/ControlledConversation'

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

vi.mock('@/api/unaskedQuestions', () => ({
  usePendingUnaskedQuestions: () => ({ data: [] }),
  useResolveUnaskedQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

let offeredCheckpoints: unknown[] = []

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  // The mutations stay real — they go through the mocked fetch, which is what these assert on.
  return { ...actual, useCheckpoints: () => ({ data: offeredCheckpoints }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
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

function calledUrl(callIndex: number): string {
  return String(fetchMock.mock.calls[callIndex][0])
}

/** What the Hub says the generated checkpoint came out as. Only `ready` is cut over to. */
let checkpointStatus: 'ready' | 'unwritten' | 'failed' = 'ready'

describe('agent conversation handoff', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [{
      id: 'conv-successor',
      agent: 'claude',
      provider_session_id: 'session-new',
      lifecycle: 'open', title: 'Continued: A conversation', title_set_by_operator: true, origin: 'handoff', attention: 'idle',
      created_at: '2026-07-29T12:05:00Z',
      updated_at: '2026-07-29T12:05:00Z',
    }, {
      id: 'conv-old',
      agent: 'claude',
      provider_session_id: 'session-old',
      lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
      created_at: '2026-07-29T11:00:00Z',
      updated_at: '2026-07-29T12:00:00Z',
    }]
    checkpointStatus = 'ready'
    offeredCheckpoints = []
    fetchMock.mockReset()
    fetchMock.mockImplementation((url, init) => {
      const path = String(url)
      if (path.endsWith('/checkpoint')) {
        return Promise.resolve(new Response(JSON.stringify({
          id: 'ckpt-1',
          conversation_id: 'conv-old',
          agent: 'claude',
          trigger: 'operator',
          status: checkpointStatus,
          visibility: 'private',
          lineage_id: 'ckpt-1',
        }), { status: 201 }))
      }
      if (path.endsWith('/cutover')) {
        return Promise.resolve(new Response(JSON.stringify({
          checkpoint_id: 'ckpt-1',
          conversation_id: 'conv-old',
          successor_conversation_id: 'conv-successor',
          queue_entry_id: 'entry-1',
          agent: 'claude',
        }), { status: 200 }))
      }
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

  it('takes a Hub-generated checkpoint and cuts over to the successor', async () => {
    const onSelectConversation = vi.fn()
    const user = userEvent.setup()
    render(
      <ControlledConversation
        agent={agent}
        conversationId="conv-old"
        onSelectConversation={onSelectConversation}
      />,
    )
    expect(screen.getAllByTestId('conversation-header')).toHaveLength(1)

    await user.click(screen.getByTestId('conversation-handoff'))

    // Two Hub calls and no agent turn. The previous design sent the agent a prompt naming a
    // skill AgentWeave never installed; generation is now the Hub's job and does not depend on
    // the agent being cooperative, or even idle.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(calledUrl(0)).toContain('/conversations/conv-old/checkpoint')
    expect(calledUrl(1)).toContain('/checkpoints/ckpt-1/cutover')

    await waitFor(() => expect(onSelectConversation).toHaveBeenCalledWith('conv-successor'))
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'Checkpoint written',
      ),
    )
  })

  it('does not cut over when the checkpoint has no written summary', async () => {
    // "unwritten" means generation produced nothing usable. Handing that to a successor would
    // rebuild the defect this capability removes: a readiness signal over an empty record.
    checkpointStatus = 'unwritten'
    const onSelectConversation = vi.fn()
    const user = userEvent.setup()
    render(
      <ControlledConversation
        agent={agent}
        conversationId="conv-old"
        onSelectConversation={onSelectConversation}
      />,
    )

    await user.click(screen.getByTestId('conversation-handoff'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(calledUrl(0)).toContain('/checkpoint')
    expect(onSelectConversation).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'no written summary',
      ),
    )
  })

  it('does not cut over when the checkpoint failed its own probes', async () => {
    checkpointStatus = 'failed'
    const user = userEvent.setup()
    const onSelectConversation = vi.fn()
    render(
      <ControlledConversation
        agent={agent}
        conversationId="conv-old"
        onSelectConversation={onSelectConversation}
      />,
    )

    await user.click(screen.getByTestId('conversation-handoff'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(onSelectConversation).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent('failed its own checks'),
    )
  })

  it('sends a plain message afterwards, with no resume prefix', async () => {
    render(
      <ControlledConversation
        agent={agent}
        conversationId="conv-successor"
        onSelectConversation={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Continue implementing the feature.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    // The successor already has the checkpoint waiting in its queue, so the operator's message
    // is only their message. It used to be prepended with instructions to find two files that
    // were never written.
    expect(triggerBody(0)).toEqual({
      agent: 'claude',
      message: 'Continue implementing the feature.',
      conversation_id: 'conv-successor',
    })
  })

  it('offers a checkpoint the Hub made on its own, and cuts over from the offer', async () => {
    // The reported failure: under "offer me one" the threshold fired, wrote a real probed
    // checkpoint, and the operator saw nothing — `checkpoint_ready` had no listener anywhere in
    // the UI, so the offer existed only in the database.
    offeredCheckpoints = [{
      id: 'ckpt-auto',
      conversation_id: 'conv-old',
      agent: 'claude',
      trigger: 'context_pressure',
      status: 'ready',
      visibility: 'private',
      lineage_id: 'ckpt-auto',
    }]
    const onSelectConversation = vi.fn()
    const user = userEvent.setup()
    render(
      <ControlledConversation
        agent={agent}
        conversationId="conv-old"
        onSelectConversation={onSelectConversation}
      />,
    )

    const banner = screen.getByTestId('conversation-banner')
    expect(banner).toHaveAttribute('data-banner-id', 'checkpoint-offered')
    // An offer is not a failure, and must not be dressed as one.
    expect(banner).toHaveAttribute('data-banner-tone', 'offer')

    await user.click(screen.getByTestId('banner-action-checkpoint-offered'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(calledUrl(0)).toContain('/checkpoints/ckpt-auto/cutover')
    await waitFor(() => expect(onSelectConversation).toHaveBeenCalledWith('conv-successor'))
  })

  it('does not offer a checkpoint that is unwritten or failed', () => {
    offeredCheckpoints = [
      { id: 'a', conversation_id: 'conv-old', agent: 'claude', trigger: 'context_pressure', status: 'unwritten', visibility: 'private', lineage_id: 'a' },
      { id: 'b', conversation_id: 'conv-old', agent: 'claude', trigger: 'context_pressure', status: 'failed', visibility: 'private', lineage_id: 'b' },
    ]
    render(
      <ControlledConversation agent={agent} conversationId="conv-old" onSelectConversation={vi.fn()} />,
    )
    // Neither has anything a successor could continue from.
    expect(screen.queryByTestId('banner-action-checkpoint-offered')).not.toBeInTheDocument()
  })

  it('warns at the threshold without spending, and the warning can be waved away', async () => {
    // The operator's point: "if I want to extend a little longer I can". Generating first billed
    // a model call whether or not they wanted one, and at a low threshold billed it again every
    // turn.
    conversations = conversations.map((c) =>
      c.id === 'conv-old' ? { ...c, checkpoint_warning: 'due' as const } : c,
    )
    const user = userEvent.setup()
    render(
      <ControlledConversation agent={agent} conversationId="conv-old" onSelectConversation={vi.fn()} />,
    )

    const banner = screen.getByTestId('conversation-banner')
    expect(banner).toHaveAttribute('data-banner-id', 'checkpoint-due')
    expect(banner).toHaveTextContent('Nothing has been written yet')

    await user.click(screen.getByTestId('banner-dismiss-checkpoint-due'))

    // Dismissal is recorded, and the banner goes on the click rather than on the next refetch.
    await waitFor(() => expect(calledUrl(0)).toContain('/dismiss-checkpoint-warning'))
    await waitFor(() =>
      expect(screen.queryByTestId('banner-dismiss-checkpoint-due')).not.toBeInTheDocument(),
    )
  })

  it('does not warn once the warning has been dismissed', () => {
    conversations = conversations.map((c) =>
      c.id === 'conv-old' ? { ...c, checkpoint_warning: 'dismissed' as const } : c,
    )
    render(
      <ControlledConversation agent={agent} conversationId="conv-old" onSelectConversation={vi.fn()} />,
    )
    // Re-asking someone who said "not yet" is the same as not letting them say it.
    expect(screen.queryByTestId('banner-dismiss-checkpoint-due')).not.toBeInTheDocument()
  })
})
