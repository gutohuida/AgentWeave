import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentOutputLine, AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse, TimelineEntry } from '@/api/agentChat'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

let outputLines: AgentOutputLine[] = []
let conversations: AgentConversation[] = []
let recordedEntries: TimelineEntry[] = []
let sseConnectionState: 'closed' | 'connecting' | 'open' | 'reconnecting' = 'open'
let roster: AgentSummary[] = []
let launchability: Record<string, { present: boolean; authorized: boolean; runnable: boolean; reason?: string }> = {}
let conversationUsage: { total_tokens: number | null; measured_turns: number } | undefined = undefined

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

vi.mock('@/api/accounting', () => ({
  useAccounting: () => ({ data: undefined }),
  useConversationAccounting: () => ({ data: conversationUsage }),
}))

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

const conversation: AgentConversation = {
  id: 'conv-old',
  agent: 'claude',
  provider_session_id: 'provider-secret-session',
  lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-08-02T10:00:00Z',
  updated_at: '2026-08-02T10:00:00Z',
}

describe('conversation controls — the resting header', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
    recordedEntries = []
    roster = [idleAgent]
    launchability = {
      claude: { present: true, authorized: true, runnable: true },
    }
    sseConnectionState = 'open'
    conversationUsage = undefined
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('shows turn actions, handoff, the active-agent indicator, and context usage at rest', async () => {
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
    expect(screen.getAllByText('claude').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Fold all turns' })).toBeInTheDocument()
    expect(screen.getByTestId('conversation-handoff')).toBeInTheDocument()

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Stop turn/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pause scroll|Resume scroll/ })).not.toBeInTheDocument()
  })

  it('has no conversation-actions overflow menu, and lists no other conversation', async () => {
    conversations = [
      conversation,
      { ...conversation, id: 'conv-second', title: 'Another conversation' },
    ]
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))

    expect(screen.queryByRole('button', { name: 'Conversation actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    // Not a switcher, not even a passive listing: conversation selection is navigation's job.
    expect(document.body.textContent).not.toContain('Another conversation')
    expect(document.body.textContent).not.toContain('conv-second')
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

  it('shows the usage indicator once this conversation has reported one', async () => {
    conversations = [
      {
        ...conversation,
        context_usage: {
          status: 'measured',
          source: 'test',
          context_tokens: 4000,
          limit_tokens: 10000,
          observed_at: 0,
        },
      },
    ]
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.getByTestId('context-usage')).toBeInTheDocument()
  })

  it('does not show another conversation’s reading, even via the agent', async () => {
    // The bug this replaced: `agent.context_usage` is one reading per agent — the newest across
    // every thread it owns — so this header showed whichever conversation last reported. Measured
    // on the trial Hub 2026-08-19: agent `verifier` had three conversations at 18.56%, 16.6% and
    // 15.9%, and all three composers showed 15.9%.
    const agentWithUsage: AgentSummary = {
      ...idleAgent,
      context_usage: {
        status: 'measured',
        source: 'test',
        context_tokens: 9000,
        limit_tokens: 10000,
        observed_at: 0,
      },
    }
    // This conversation has produced no reading of its own.
    conversations = [conversation]
    render(<AgentOutputPanel agent={agentWithUsage} conversationId="conv-old" />)

    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.queryByTestId('context-usage')).not.toBeInTheDocument()
  })

  it('follows the conversation being viewed, not the newest one', async () => {
    conversations = [
      {
        ...conversation,
        context_usage: {
          status: 'measured',
          source: 'test',
          context_tokens: 1000,
          limit_tokens: 10000,
          observed_at: 0,
        },
      },
      {
        ...conversation,
        id: 'conv-second',
        title: 'Another conversation',
        context_usage: {
          status: 'measured',
          source: 'test',
          context_tokens: 9000,
          limit_tokens: 10000,
          observed_at: 99,
        },
      },
    ]

    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('context-usage')).toHaveTextContent('10%'))

    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-second" />)
    await waitFor(() => expect(screen.getByTestId('context-usage')).toHaveTextContent('90%'))
  })
})

describe('conversation controls — whole-conversation token total', () => {
  beforeEach(() => {
    outputLines = []
    conversations = [conversation]
    recordedEntries = []
    roster = [idleAgent]
    launchability = { claude: { present: true, authorized: true, runnable: true } }
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('renders nothing while the rollup has not loaded or has no measured turns', async () => {
    conversationUsage = undefined
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.queryByTestId('conversation-token-total')).not.toBeInTheDocument()

    conversationUsage = { total_tokens: null, measured_turns: 0 }
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(screen.queryByTestId('conversation-token-total')).not.toBeInTheDocument()
  })

  it('shows the running total once the conversation has at least one measured turn', async () => {
    conversationUsage = { total_tokens: 42_300, measured_turns: 3 }
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    await waitFor(() => expect(screen.getByTestId('session-continuity')).toHaveTextContent('A conversation'))
    expect(screen.getByTestId('conversation-token-total')).toHaveTextContent('42,300 tokens')
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

  it('keeps following when the newest folded outbound message expands', () => {
    const originalResizeObserver = globalThis.ResizeObserver
    let resizeCallback: ResizeObserverCallback | null = null
    class DisclosureResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    ;(globalThis as unknown as { ResizeObserver: typeof DisclosureResizeObserver }).ResizeObserver =
      DisclosureResizeObserver
    recordedEntries = [
      {
        id: 'outbound-fold',
        kind: 'outbound_peer',
        participant: 'codex',
        subject: 'One more month',
        content: 'Name one more month you like.',
        timestamp: '2026-08-06T00:00:01Z',
        delivery_state: 'delivered',
        run_id: 'run-fold',
      },
    ]
    try {
      render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
      const output = screen.getByTestId('conversation-output')
      let top = 960
      Object.defineProperty(output, 'scrollTop', {
        configurable: true,
        get: () => top,
        set: (next: number) => { top = next },
      })
      Object.defineProperty(output, 'clientHeight', { configurable: true, value: 40 })
      Object.defineProperty(output, 'scrollHeight', {
        configurable: true,
        get: () =>
          screen.queryByText('Name one more month you like.') === null ? 1000 : 1180,
      })
      fireEvent.scroll(output)

      fireEvent.click(screen.getByText('One more month'))
      // Match the browser's intermediate anchor shift before ResizeObserver reports the turn's
      // new height. That scroll event is layout, not the operator leaving the bottom.
      output.scrollTop = 1000
      fireEvent.scroll(output)
      act(() => {
        if (!resizeCallback) throw new Error('turn ResizeObserver was not installed')
        resizeCallback([], {} as ResizeObserver)
      })

      expect(screen.getByText('Name one more month you like.')).toBeInTheDocument()
      expect(output.scrollTop).toBe(1180)
      expect(screen.queryByRole('button', { name: 'Jump to newest' })).not.toBeInTheDocument()
    } finally {
      globalThis.ResizeObserver = originalResizeObserver
    }
  })

  it('does not move the viewport when a folded outbound message expands while reading above', async () => {
    recordedEntries = [
      {
        id: 'outbound-fold-away',
        kind: 'outbound_peer',
        participant: 'codex',
        subject: 'Earlier delegation',
        content: 'Full content from earlier in the conversation.',
        timestamp: '2026-08-06T00:00:01Z',
        delivery_state: 'delivered',
        run_id: 'run-fold-away',
      },
    ]
    render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')
    setScrollGeometry(output, { scrollTop: 200, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)
    await screen.findByRole('button', { name: 'Jump to newest' })

    fireEvent.click(screen.getByText('Earlier delegation'))

    expect(screen.getByText('Full content from earlier in the conversation.')).toBeInTheDocument()
    expect(output.scrollTop).toBe(200)
  })

  /**
   * Operator, 2026-08-20: "the scroll is behaving weirdly... when I scroll all the way down it
   * suddenly jumps up a little bit. Feels like a bouncing pattern."
   *
   * The landing effect — "opening a conversation shows its newest entry" — listed `scrollToNewest`
   * as a dependency. That callback's identity changes with `tailSpacer`, which is re-measured on
   * every render of a streaming response, so an effect meant to fire on arrival re-fired
   * throughout a turn: it yanked the viewport to the newest entry and forced `autoscroll` back on,
   * against a `handleScroll` that had just turned it off. Reading further up the conversation was
   * the thing this made impossible.
   */
  it('does not re-land on the newest entry while the operator is reading further up', () => {
    recordedEntries = [timelineEntry('1')]
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    // The turn's measured height is what drives `tailSpacer`, and a growing answer changes it on
    // every render — which is exactly what used to give `scrollToNewest` a new identity and
    // re-run the landing effect. Reproducing the bounce requires that measurement to move, so
    // the height is read from a variable the test advances.
    let turnHeight = 120
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get(this: HTMLElement) {
        return this.hasAttribute?.('data-turn-boundary') ? turnHeight : 0
      },
    })
    try {
      setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 600 })
      recordedEntries = [timelineEntry('1'), timelineEntry('2')]
      rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)

      // The operator scrolls up to read something, which turns following off.
      setScrollGeometry(output, { scrollTop: 120, scrollHeight: 1000, clientHeight: 600 })
      fireEvent.scroll(output)
      expect(output.scrollTop).toBe(120)

      // The answer keeps streaming: entries land, the turn grows, and the spacer shrinks with it.
      // The spacer is what gives `scrollToNewest` a new identity, and re-measuring it needs the
      // entry count to move — which is why this advances both. None of it is an arrival at a
      // conversation, so none of it may scroll.
      // Single-digit ids: `timelineEntry` interpolates the id into the seconds field.
      for (const [id, height] of [['3', 200], ['4', 280], ['5', 360]] as const) {
        turnHeight = height
        recordedEntries = [...recordedEntries, timelineEntry(id)]
        rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
      }

      expect(output.scrollTop).toBe(120)
    } finally {
      if (original) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', original)
      else Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight')
    }
  })

  it('still lands on the newest entry when the conversation itself changes', () => {
    // The other half of the same boundary: suppressing the re-fire must not suppress the arrival.
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 40 })
    recordedEntries = [timelineEntry('1')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    expect(output.scrollTop).toBe(1000)

    setScrollGeometry(output, { scrollTop: 120, scrollHeight: 1000, clientHeight: 40 })
    fireEvent.scroll(output)

    recordedEntries = [timelineEntry('9')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-new" />)

    expect(output.scrollTop).toBe(1000)
  })

  /**
   * Operator, 2026-08-18: "When we send a message the screen to scroll up and leave a big space
   * for the response... the message that I just sent to look like the first message."
   *
   * The tail spacer is what makes that possible: enough room below the newest turn for it to sit
   * at the top of the viewport, and no more, so it shrinks to nothing as the answer grows and
   * ordinary bottom-following takes over without a jump.
   */
  it('reserves room below the newest turn so it can sit at the top of the viewport', () => {
    recordedEntries = [timelineEntry('1')]
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')

    expect(output.querySelector('[data-turn-boundary]')).not.toBeNull()

    // Patched on the prototype rather than on the node: React replaces the turn element on
    // rerender, so a property defined on the instance is gone by the time the effect measures.
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      get(this: HTMLElement) {
        return this.hasAttribute?.('data-turn-boundary') ? 120 : 0
      },
    })
    try {
      setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 600 })
      recordedEntries = [timelineEntry('1'), timelineEntry('2')]
      rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)

      // 600 viewport - 120 turn - 24 gap.
      expect(screen.getByTestId('conversation-tail-spacer')).toHaveStyle({ height: '456px' })
    } finally {
      if (original) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', original)
      else Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight')
    }
  })

  it('reserves nothing when the newest turn has not been laid out yet', () => {
    // offsetHeight 0 means "not measured", not "zero tall". Treating it as a real height would
    // reserve a viewport-sized void and pin a turn nobody can see, so this falls back to plain
    // bottom-following — which is also what keeps every other test in this file honest.
    recordedEntries = [timelineEntry('1')]
    const { rerender } = render(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)
    const output = screen.getByTestId('conversation-output')
    setScrollGeometry(output, { scrollTop: 0, scrollHeight: 1000, clientHeight: 600 })

    recordedEntries = [timelineEntry('1'), timelineEntry('2')]
    rerender(<AgentOutputPanel agent={idleAgent} conversationId="conv-old" />)

    expect(screen.getByTestId('conversation-tail-spacer')).toHaveStyle({ height: '0px' })
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
