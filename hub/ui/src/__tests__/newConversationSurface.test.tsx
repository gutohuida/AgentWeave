import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 1, runner_id: 'runner-claude' },
      { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, color_index: 3, runner_id: 'runner-codex' },
    ],
  }),
}))
vi.mock('@/api/runners', () => ({
  useRunners: () => ({
    data: [
      { id: 'runner-claude', cli: 'claude', model: 'claude-opus-5' },
      { id: 'runner-codex', cli: 'codex', model: 'gpt-5' },
    ],
  }),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

/** The surface is controlled — the destination owns which agent the unsent message is for. This
 *  plays App's half of that, so a test can click a chip and see the surface follow. */
function Controlled({
  agent: initial,
  onStarted = vi.fn(),
  onChooseAgent,
}: {
  agent: string | null
  onStarted?: (agent: string, conversationId: string) => void
  onChooseAgent?: (agent: string) => void
}) {
  const [agent, setAgent] = useState<string | null>(initial)
  return (
    <NewConversationSurface
      projectId="proj-a"
      agent={agent}
      onChooseAgent={(next) => {
        setAgent(next)
        onChooseAgent?.(next)
      }}
      onStarted={onStarted}
    />
  )
}

function renderSurface(agent: string | null, onStarted = vi.fn()) {
  render(<Controlled agent={agent} onStarted={onStarted} />)
  return { onStarted }
}

describe('starting a conversation', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-fresh' }), {
        status: 200,
      }),
    )
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('leads with the composer, not an empty transcript', () => {
    renderSurface('claude')
    expect(screen.getByTestId('new-conversation-surface')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-output')).not.toBeInTheDocument()
  })

  it('asks what the bound agent should work on, by name', () => {
    renderSurface('claude')
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'What should claude work on?',
    )
  })

  it('asks who should work on it when no agent is bound, and follows the choice', async () => {
    renderSurface(null)
    // The headline is the instruction here, not decoration above one.
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'Who should work on this?',
    )

    fireEvent.click(screen.getByTestId('new-conversation-agent-codex'))
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
        'What should codex work on?',
      ),
    )
  })

  it('is already bound when started from an agent’s row, and needs no choice', async () => {
    const { onStarted } = renderSurface('claude')
    expect(screen.queryByTestId('composer-disabled-reason')).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Look at the flaky test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      agent: 'claude',
      message: 'Look at the flaky test',
    })
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh'))
  })

  it('requires an agent when started from the recency view, and says so', async () => {
    renderSurface(null)
    expect(screen.getByTestId('composer-disabled-reason')).toHaveTextContent(
      'Choose an agent to start',
    )

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Who is listening?' } })
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('new-conversation-agent-codex'))
    await waitFor(() =>
      expect(screen.queryByTestId('composer-disabled-reason')).not.toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).agent).toBe('codex')
  })

  it('creates nothing when the operator leaves without sending', () => {
    const { unmount } = render(<Controlled agent="claude" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'On second thoughts…' } })
    unmount()
    // A conversation is created by its first message; abandoning the surface leaves no row.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('treats a pre-selected agent as a default, not a lock', async () => {
    // Operator, 2026-08-08: "I like the way that it pre select but it shouldn't lock. If I change
    // the conversation should be directed elsewhere." Arriving from codex's row menu and finding
    // claude's chip dead is worse than arriving with nothing selected at all.
    const onChooseAgent = vi.fn()
    const onStarted = vi.fn()
    render(<Controlled agent="codex" onStarted={onStarted} onChooseAgent={onChooseAgent} />)
    expect(screen.getByTestId('new-conversation-agent-codex')).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByTestId('new-conversation-agent-claude'))
    expect(onChooseAgent).toHaveBeenCalledWith('claude')
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-agent-claude')).toHaveAttribute('aria-pressed', 'true'),
    )
    expect(screen.getByTestId('new-conversation-agent-codex')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent(
      'What should claude work on?',
    )

    // And the message actually goes where the operator redirected it.
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Take this one instead' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).agent).toBe('claude')
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith('claude', 'conv-fresh'))
  })

  it('keeps the typed message when the agent is changed', async () => {
    render(<Controlled agent="codex" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Half-written thought' } })

    fireEvent.click(screen.getByTestId('new-conversation-agent-claude'))
    await waitFor(() =>
      expect(screen.getByTestId('new-conversation-headline')).toHaveTextContent('claude'),
    )
    // Retargeting is a change of recipient, not a fresh start.
    expect(screen.getByRole('textbox')).toHaveValue('Half-written thought')
  })
})
