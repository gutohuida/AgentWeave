import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentOutputLine, AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse, TimelineEntry } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'
import { ControlledConversation } from './support/ControlledConversation'

let outputLines: AgentOutputLine[] = []
let conversations: AgentConversation[] = []
let recordedEntries: TimelineEntry[] = []
let sseConnectionState: 'closed' | 'connecting' | 'open' | 'reconnecting' = 'open'
let roster: AgentSummary[] = []
let launchability: Record<string, { present: boolean; authorized: boolean; runnable: boolean; reason?: string }> = {}

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return {
    ...actual,
    useAgentOutput: () => ({ lines: outputLines, isLoading: false }),
    useAgents: () => ({ data: roster }),
    useAgentLaunchability: () => ({ data: { agents: launchability } }),
    useAgentTimeline: () => ({ data: [] }),
    useAgentSessions: () => ({ data: { sessions: [] }, isLoading: false }),
  }
})

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversations[0]?.id ?? null,
    session_id: conversations[0]?.provider_session_id ?? null,
    agent: 'claude',
    entries: recordedEntries,
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
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))

vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [], isLoading: false }),
  useBindAgentRunner: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useUpdateAgentWaiting: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  MIN_WAITING_SECONDS: 10,
  MAX_WAITING_SECONDS: 600,
}))

vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: undefined }) }
})

vi.mock('@/api/charters', () => ({
  useCharters: () => ({ data: [], isLoading: false }),
  useBindAgentCharter: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
}))

vi.mock('@/api/workspace', () => ({
  useWorkspacePaths: () => ({ data: [] }),
}))

vi.mock('@/hooks/useSSE', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useSSE')>()
  return {
    ...actual,
    useSSEConnectionState: () => sseConnectionState,
  }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

const idleAgent: AgentSummary = {
  name: 'claude',
  status: 'idle',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

const runningAgent: AgentSummary = { ...idleAgent, status: 'running' }
const manualAgent: AgentSummary = { ...idleAgent, runner: 'manual' }

const conversation: AgentConversation = {
  id: 'conv-old',
  agent: 'claude',
  provider_session_id: 'provider-secret-session',
  lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-08-02T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
}

describe('conversation controls — placement and overflow menu', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
    recordedEntries = []
    roster = [idleAgent]
    launchability = {
      claude: { present: true, authorized: true, runnable: true },
    }
    sseConnectionState = 'open'
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('shows turn actions, the active-agent indicator, and context usage in the header at rest', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Conversation actions' })).toBeInTheDocument()
    expect(screen.getAllByText('claude').length).toBeGreaterThan(0)

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Handoff/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fold all turns' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Stop turn/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pause scroll|Resume scroll/ })).not.toBeInTheDocument()
  })

  it('shows stop only while the agent is running', () => {
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(screen.queryByRole('button', { name: /Stop/ })).not.toBeInTheDocument()

    rerender(<AgentOutputPanel agent={runningAgent} conversationId="conv-old" />)
    expect(screen.getByRole('button', { name: /Stop/ })).toBeInTheDocument()
  })

  it('hides provider session identity from the resting surface', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    expect(document.body.textContent).not.toContain(conversation.provider_session_id)
    expect(screen.queryByText(/session:/i)).not.toBeInTheDocument()
  })

  it('opens the overflow menu with items in fixed order, keyboard-activatable, focus returns to trigger on close', async () => {
    const user = userEvent.setup()
    render(<ControlledConversation agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    const trigger = screen.getByRole('button', { name: 'Conversation actions' })
    await user.click(trigger)

    const menu = await screen.findByRole('menu')
    expect(menu).toBeInTheDocument()

    const items = screen.getAllByRole('menuitem').map((item) => item.textContent ?? '')
    expect(items[0]).toContain('New conversation')
    expect(items[1]).toContain('conv-old')
    expect(items[2]).toContain('Handoff')
    expect(items[3]).toContain('Agent details')
    expect(items).toHaveLength(4)

    // On open, focus lands on the menu content itself; one ArrowDown moves
    // it to the first item, which can then be activated by the keyboard alone.
    const newConversationItem = screen.getByRole('menuitem', { name: 'New conversation' })
    await user.keyboard('{ArrowDown}')
    await waitFor(() => expect(newConversationItem).toHaveFocus())
    await user.keyboard('{Enter}')
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent(
        'Next message starts a fresh conversation',
      ),
    )
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())

    // Re-open and close with Escape — focus must return to the trigger.
    await user.click(trigger)
    await screen.findByRole('menu')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('selects a different conversation from the overflow menu', async () => {
    conversations = [
      conversation,
      { ...conversation, id: 'conv-second', provider_session_id: 'provider-second' },
    ]
    const onSelectConversation = vi.fn()
    const user = userEvent.setup()
    render(
      <ControlledConversation
        agent={idleAgent}
        conversationId="conv-old"
        onSelectConversation={onSelectConversation}
      />,
    )
    await waitFor(() =>
      expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'),
    )

    await user.click(screen.getByRole('button', { name: 'Conversation actions' }))
    await user.click(await screen.findByRole('menuitem', { name: /conv-second/ }))

    await waitFor(() => expect(onSelectConversation).toHaveBeenCalledWith('conv-second'))
  })

  it('shows an unavailable action disabled with its reason', async () => {
    const user = userEvent.setup()
    render(<AgentOutputPanel agent={manualAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    await user.click(screen.getByRole('button', { name: 'Conversation actions' }))
    const handoffItem = await screen.findByRole('menuitem', { name: /Handoff/ })
    expect(handoffItem).toHaveAttribute('aria-disabled', 'true')
    expect(handoffItem).toHaveTextContent('Requires an automatically managed runner')
  })

  it('opens agent details without unmounting the conversation, and returns focus on close', async () => {
    const user = userEvent.setup()
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    const trigger = screen.getByRole('button', { name: 'Conversation actions' })
    await user.click(trigger)
    await user.click(await screen.findByRole('menuitem', { name: 'Agent details' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('claude details')
    // The conversation underneath is still mounted, not navigated away from.
    expect(screen.getByTestId('conversation-header')).toBeInTheDocument()
    expect(screen.getByTestId('conversation-output')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close details' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('offers no way to redirect a message to a different agent', async () => {
    // Operator: "Let's remove the ability and the buttons that enable the user from one screen
    // to send message to another agent. Is counter intuitive." A retargeted message left no
    // trace in the conversation the operator was looking at.
    const codexAgent: AgentSummary = { ...idleAgent, name: 'codex', runner: 'codex' }
    roster = [idleAgent, codexAgent]
    launchability.codex = { present: true, authorized: true, runnable: true }
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      status: 'started',
      conversation_id: 'conv-claude',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const user = userEvent.setup()

    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    expect(screen.queryByRole('button', { name: /^Target agent:/ })).not.toBeInTheDocument()

    await user.type(screen.getByRole('textbox'), 'stays here')
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    // Always the agent whose conversation this is, and it continues that conversation.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(request.body as string)).toEqual({
      agent: 'claude',
      message: 'stays here',
      conversation_id: 'conv-old',
    })
    expect(conversation.agent).toBe('claude')
  })
})

describe('conversation controls — context usage placement', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
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

  it('renders nothing when no context-usage event has been received', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.queryByTestId('context-usage')).not.toBeInTheDocument()
  })

  it('shows the usage indicator once a context-usage event has been reported', async () => {
    const agentWithUsage: AgentSummary = {
      ...idleAgent,
      context_usage: {
        status: 'measured',
        source: 'test',
        context_tokens: 4000,
        limit_tokens: 10000,
        observed_at: 0,
      },
    }
    render(<AgentOutputPanel agent={agentWithUsage} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.getByTestId('context-usage')).toBeInTheDocument()
  })
})

describe('conversation controls — banner stack', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
    recordedEntries = []
    sseConnectionState = 'open'
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('stacks simultaneous conditions in a stable order and drops only the cleared one', async () => {
    fetchMock.mockResolvedValue(new Response('failed', { status: 503 }))
    sseConnectionState = 'reconnecting'
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(2))
    let banners = screen.getAllByRole('alert')
    expect(banners[0]).toHaveTextContent('Failed to send message')
    expect(banners[1]).toHaveTextContent('disconnected')

    sseConnectionState = 'open'
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)

    await waitFor(() => expect(screen.getAllByRole('alert')).toHaveLength(1))
    banners = screen.getAllByRole('alert')
    expect(banners[0]).toHaveTextContent('Failed to send message')

    errorSpy.mockRestore()
  })
})

describe('conversation controls — autoscroll follows scroll position', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
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

  function setScrollGeometry(el: HTMLElement, { scrollTop, scrollHeight, clientHeight }: {
    scrollTop: number
    scrollHeight: number
    clientHeight: number
  }) {
    let top = scrollTop
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => top,
      set: (next: number) => { top = next },
    })
    Object.defineProperty(el, 'scrollHeight', { configurable: true, value: scrollHeight })
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: clientHeight })
  }

  function timelineEntry(id: string): TimelineEntry {
    return {
      id,
      kind: 'agent_output',
      content: `entry ${id}`,
      timestamp: `2026-08-06T00:00:0${id}Z`,
      delivery_state: 'delivered',
    }
  }

  it('follows the conversation entries it renders, not the raw output log', () => {
    // The effect used to depend on `lines` from `useAgentOutput` — the legacy output stream,
    // which is not what this view renders. Driving content through `recordedEntries` is what
    // actually exercises the conversation, and is why the previous version of this test could
    // not observe the defect.
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 40 })
    recordedEntries = [timelineEntry('1')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(output.scrollTop).toBe(1000)

    // Scrolled away — a new entry must not move the viewport.
    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)
    recordedEntries = [...recordedEntries, timelineEntry('2')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(output.scrollTop).toBe(0)

    // Back at the bottom — following resumes.
    setScrollGeometry(output, { scrollTop: 960, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)
    recordedEntries = [...recordedEntries, timelineEntry('3')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(output.scrollTop).toBe(1000)
  })

  it('lands at the newest entry when the conversation opens, and resumes following', () => {
    recordedEntries = [timelineEntry('1'), timelineEntry('2'), timelineEntry('3')]
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    // Put the operator partway up a long history with following suspended.
    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)
    expect(output.scrollTop).toBe(0)

    // Switching to another agent's conversation re-runs the open path.
    rerender(<AgentOutputPanel agent={{ ...idleAgent, name: 'other' }} conversationId="conv-old" />)

    expect(output.scrollTop).toBe(1000)
    expect(screen.queryByRole('button', { name: 'Jump to newest' })).not.toBeInTheDocument()
  })

  it('offers a way back to the newest entry only while following is suspended', async () => {
    recordedEntries = [timelineEntry('1')]
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    // Following: no control.
    expect(screen.queryByRole('button', { name: 'Jump to newest' })).not.toBeInTheDocument()

    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)

    const jump = await screen.findByRole('button', { name: 'Jump to newest' })
    fireEvent.click(jump)

    expect(output.scrollTop).toBe(1000)
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Jump to newest' })).not.toBeInTheDocument(),
    )
  })

  it('does not reintroduce a pause or resume scroll toggle', () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(
      screen.queryByRole('button', { name: /Pause scroll|Resume scroll/ }),
    ).not.toBeInTheDocument()
  })
})
