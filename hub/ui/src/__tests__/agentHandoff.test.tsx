import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentOutputLine, AgentSession, AgentSummary } from '@/api/agents'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

let outputLines: AgentOutputLine[] = []
let sessions: AgentSession[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: outputLines, isLoading: false }),
    useAgentSessions: () => ({ data: { sessions } }),
    useAgents: () => ({ data: [] }),
    useAgentTimeline: () => ({ data: [] }),
  }
})

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return {
    ...actual,
    useAgentChatHistory: () => ({ data: undefined, isLoading: false }),
    useAgentRecentChat: () => ({ data: undefined, isLoading: false }),
  }
})

vi.mock('@/api/queue', () => ({
  useQueueStatus: () => ({ data: undefined }),
  withdrawQueueEntry: vi.fn(),
}))

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
    sessions = [{ id: 'session-old', type: 'claude', path: 'old.json' }]
    fetchMock.mockReset()
    fetchMock.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ status: 'running' }), { status: 200 })),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      projectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('checkpoints the old session and resumes the handoff in exactly one new session', async () => {
    const view = render(<AgentOutputPanel agent={agent} />)

    const selector = await screen.findByRole('combobox')
    await waitFor(() => expect(selector).toHaveValue('session-old'))

    fireEvent.click(screen.getByRole('button', { name: 'Handoff' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(triggerBody(0)).toMatchObject({
      agent: 'claude',
      session_mode: 'resume',
      session_id: 'session-old',
    })
    expect(triggerBody(0).message).toContain('aw-checkpoint skill')
    await waitFor(() => expect(selector).toHaveValue('__new__'))
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
    view.rerender(<AgentOutputPanel agent={agent} />)

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
      session_mode: 'new',
    })
    expect(triggerBody(1)).not.toHaveProperty('session_id')
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
    sessions = [
      { id: 'session-new', type: 'claude', path: 'new.json' },
      ...sessions,
    ]
    view.rerender(<AgentOutputPanel agent={agent} />)

    await waitFor(() => expect(selector).toHaveValue('session-new'))

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'And now continue normally.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(triggerBody(2)).toEqual({
      agent: 'claude',
      message: 'And now continue normally.',
      session_mode: 'resume',
      session_id: 'session-new',
    })
  })
})
