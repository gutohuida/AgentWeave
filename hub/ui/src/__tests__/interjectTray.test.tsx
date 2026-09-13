/**
 * F345 — operator, 2026-09-13: "When I have an agent using ask user the question box is kind of
 * hard stuck. It eats the screen away with a big black rectangle. It would be nice to have it
 * floating on top of the agent conversation but we should be able also to scroll to the end of
 * the conversations."
 *
 * The question and permission cards used to stack in the composer's column, which cannot shrink:
 * an unbounded card took the transcript's height, down to nothing, and could push the composer
 * off the panel. They now float over the conversation's foot in a tray, and the tray's height is
 * reserved below the newest entry so the conversation's end still scrolls into view above it.
 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { AgentConversation, ChatHistoryResponse, TimelineEntry } from '@/api/agentChat'
import type { PermissionRequest } from '@/api/permissions'
import type { Question } from '@/api/questions'
import { useConfigStore } from '@/store/configStore'
import { AgentOutputPanel } from '@/components/agents/AgentOutputPanel'

let openQuestions: Question[] = []
let permissionRequests: PermissionRequest[] = []
let entries: TimelineEntry[] = []

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

const conversation: AgentConversation = {
  id: 'conv-1',
  agent: 'architect',
  provider_session_id: 'provider-1',
  lifecycle: 'open', title: 'A conversation', title_set_by_operator: false, origin: 'operator', attention: 'idle',
  created_at: '2026-09-13T10:00:00Z',
  updated_at: '2026-09-13T10:00:00Z',
}

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const history = (): ChatHistoryResponse => ({
    conversation_id: conversation.id,
    session_id: conversation.provider_session_id,
    agent: conversation.agent,
    entries,
    runs: {},
  })
  return {
    ...actual,
    useAgentConversations: () => ({ data: [conversation] }),
    useAgentChatHistory: () => ({ data: history(), isLoading: false }),
    useAgentRecentChat: () => ({ data: history(), isLoading: false }),
  }
})

vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: openQuestions }),
  useAnswerQuestion: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/permissions', () => ({
  usePendingPermissionRequests: () => ({ data: permissionRequests }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
  useDismissPermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/checkpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/checkpoints')>()
  return { ...actual, useCheckpoints: () => ({ data: [] }) }
})

vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
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

;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = vi.fn()

const agent: AgentSummary = {
  name: 'architect',
  status: 'running',
  message_count: 0,
  active_task_count: 0,
  runner: 'claude',
}

function askUser(overrides: Partial<Question> = {}): Question {
  return {
    id: 'q-1',
    project_id: 'proj-test',
    from_agent: 'architect',
    question: 'Which way should the migration go?',
    header: 'Migration',
    blocking: true,
    answered: false,
    multi_select: false,
    options: [
      { label: 'Forward', description: 'Add the column' },
      { label: 'Backward', description: 'Drop it' },
    ],
    created_at: '2026-09-13T10:01:00Z',
    ...overrides,
  }
}

function entry(id: string): TimelineEntry {
  return {
    id,
    kind: 'agent_output',
    content: `entry ${id}`,
    timestamp: `2026-09-13T10:00:0${id}Z`,
    delivery_state: 'delivered',
  }
}

/** jsdom lays nothing out. Heights are read from the prototype so React's replacement of a node
 *  between renders cannot drop them. The panel is laid out as a browser would: a 50px header, a
 *  composer area of 200px plus the tray and its 8px gap while the tray is inline, and whatever
 *  `room` says is left for the conversation. */
const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')
const originalClientHeight = Object.getOwnPropertyDescriptor(Element.prototype, 'clientHeight')
const originalGetClientRects = Element.prototype.getClientRects
const HEADER_PX = 50
const COMPOSER_PX = 200
function layOut({ tray, turn, room = () => 600 }: { tray: number; turn: number; room?: () => number }) {
  const is = (el: Element, id: string) => el.getAttribute?.('data-testid') === id
  const inlineNow = () => document.querySelector('[data-testid="conversation-interject-inline"]') !== null
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) {
      if (this.classList?.contains('conversation-interject-tray-column')) return tray
      if (this.hasAttribute?.('data-turn-boundary')) return turn
      if (is(this, 'conversation-header')) return HEADER_PX
      if (is(this, 'conversation-composer-area')) return COMPOSER_PX + (inlineNow() ? tray + 8 : 0)
      return 0
    },
  })
  Object.defineProperty(Element.prototype, 'clientHeight', {
    configurable: true,
    get(this: Element) {
      return is(this, 'conversation-panel') ? room() + HEADER_PX + COMPOSER_PX : 0
    },
  })
  // Laid out: the panel reads "no rects" as "not laid out yet" and decides nothing from it.
  Element.prototype.getClientRects = function (this: Element) {
    return (is(this, 'conversation-panel') ? [{}] : []) as unknown as DOMRectList
  }
}

/** A ResizeObserver that can be fired by hand — the setup file's stub never calls back. */
function recordResizeObservers() {
  const callbacks: ResizeObserverCallback[] = []
  const original = globalThis.ResizeObserver
  class Recording {
    constructor(callback: ResizeObserverCallback) {
      callbacks.push(callback)
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  ;(globalThis as unknown as { ResizeObserver: typeof Recording }).ResizeObserver = Recording
  return {
    fire: () => act(() => callbacks.forEach((cb) => cb([], {} as ResizeObserver))),
    restore: () => {
      globalThis.ResizeObserver = original
    },
  }
}

function viewport(el: HTMLElement, clientHeight: number) {
  let top = 0
  Object.defineProperty(el, 'scrollTop', { configurable: true, get: () => top, set: (v: number) => { top = v } })
  Object.defineProperty(el, 'scrollHeight', { configurable: true, value: 2000 })
  Object.defineProperty(el, 'clientHeight', { configurable: true, value: clientHeight })
}

describe('interjections float over the conversation', () => {
  beforeEach(() => {
    openQuestions = []
    permissionRequests = []
    entries = []
    useConfigStore.setState({ apiKey: 'aw_live_test', isConfigured: true, selectedProjectId: 'proj-test' })
  })

  afterEach(() => {
    if (originalOffsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
    else Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight')
    if (originalClientHeight) Object.defineProperty(Element.prototype, 'clientHeight', originalClientHeight)
    Element.prototype.getClientRects = originalGetClientRects
  })

  it('puts a pending question in the tray over the conversation, not in the composer column', () => {
    openQuestions = [askUser()]
    const { container } = render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    const tray = screen.getByTestId('conversation-interject-tray')
    expect(tray).toContainElement(screen.getByTestId('agent-question-q-1'))
    // The composer's column no longer holds it, so the card cannot take the composer's height.
    const composerColumn = container.querySelector('.conversation-composer-fade') as HTMLElement
    expect(composerColumn).not.toContainElement(screen.getByTestId('agent-question-q-1'))
    expect(composerColumn.querySelector('textarea')).not.toBeNull()
  })

  it('puts a permission request in the same tray', () => {
    permissionRequests = [
      {
        id: 'perm-1',
        agent: 'architect',
        run_id: 'run-1',
        tool_name: 'Bash',
        tool_use_id: 'toolu-1',
        tool_input: { command: 'git push' },
        status: 'pending',
        dismissed: false,
        created_at: '2026-09-13T10:01:00Z',
        decided_at: null,
        decided_by: null,
      },
    ]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.getByTestId('conversation-interject-tray')).toContainElement(
      screen.getByTestId('permission-request-perm-1'),
    )
  })

  it('shows no tray, and reserves nothing, while nothing is being asked', () => {
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.queryByTestId('conversation-interject-tray')).toBeNull()
    expect(screen.getByTestId('conversation-tray-inset')).toHaveStyle({ height: '0px' })
  })

  it('shows no tray for another agent’s question', () => {
    openQuestions = [askUser({ from_agent: 'someone-else' })]
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.queryByTestId('conversation-interject-tray')).toBeNull()
  })

  it('reserves the tray’s height below the newest entry, so the end still scrolls into view', () => {
    layOut({ tray: 200, turn: 120 })
    entries = [entry('1')]
    openQuestions = [askUser()]
    const { rerender } = render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
    viewport(screen.getByTestId('conversation-output'), 600)

    entries = [entry('1'), entry('2')]
    rerender(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    // The tray's 200px plus its 8px bottom margin is kept clear below the conversation...
    expect(screen.getByTestId('conversation-tray-inset')).toHaveStyle({ height: '208px' })
    // ...and the room that pins the newest turn to the top is what is left above the tray:
    // 600 viewport - 208 tray - 120 turn - 24 gap. Without the subtraction the turn would be
    // pinned with its foot under the tray.
    expect(screen.getByTestId('conversation-tail-spacer')).toHaveStyle({ height: '248px' })
  })
})

describe('a conversation too short for the tray to float over it', () => {
  // Measured by an independent test pass on the first version: at 560px wide the floating column
  // showed 41px of an eight-option question, and at 420×560 — where the project rail stacks above
  // the panel — nothing at all, with its fold control unreachable.
  beforeEach(() => {
    openQuestions = [askUser()]
    permissionRequests = []
    entries = [entry('1')]
    useConfigStore.setState({ apiKey: 'aw_live_test', isConfigured: true, selectedProjectId: 'proj-test' })
  })

  afterEach(() => {
    if (originalOffsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', originalOffsetHeight)
    else Reflect.deleteProperty(HTMLElement.prototype, 'offsetHeight')
    if (originalClientHeight) Object.defineProperty(Element.prototype, 'clientHeight', originalClientHeight)
    Element.prototype.getClientRects = originalGetClientRects
  })

  it('puts the question in the composer column instead, and reserves nothing over the conversation', () => {
    layOut({ tray: 144, turn: 120, room: () => 150 })
    const { container } = render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    const inline = screen.getByTestId('conversation-interject-inline')
    expect(inline).toContainElement(screen.getByTestId('agent-question-q-1'))
    expect(container.querySelector('.conversation-composer-fade')).toContainElement(inline)
    expect(screen.queryByTestId('conversation-interject-tray')).toBeNull()
    expect(screen.getByTestId('conversation-tray-inset')).toHaveStyle({ height: '0px' })
  })

  it('takes the room the conversation had, not the composer’s', () => {
    // The send button is what confirms a chosen option, so pushing the composer off the panel makes
    // the question unanswerable. 100px of room: the question gets 100 - 8 (its gap) = 92px.
    layOut({ tray: 300, turn: 120, room: () => 100 })
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.getByTestId('conversation-interject-inline')).toHaveStyle({ maxHeight: '92px' })
    // The conversation's padding gives way too; around no visible content it only pushed.
    expect(screen.getByTestId('conversation-output').className).not.toContain('py-[22px]')
  })

  it('keeps its header and first line even when there is no room at all', () => {
    layOut({ tray: 300, turn: 120, room: () => 0 })
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.getByTestId('conversation-interject-inline')).toHaveStyle({ maxHeight: '72px' })
  })

  it('never asks for more than its largest inline height', () => {
    layOut({ tray: 300, turn: 120, room: () => 230 })
    render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)

    expect(screen.getByTestId('conversation-interject-inline')).toHaveStyle({ maxHeight: '144px' })
  })

  it('stays put rather than flipping back and forth once it has moved', () => {
    // Deciding from the conversation body's height flips or sticks: inline, the tray has taken
    // its own height out of the body, and once the body bottoms out the shortfall is invisible.
    // The room is read from sizes the tray does not move, so repeated measurement agrees.
    const observers = recordResizeObservers()
    try {
      layOut({ tray: 144, turn: 120, room: () => 150 })
      render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
      expect(screen.getByTestId('conversation-interject-inline')).toBeInTheDocument()

      observers.fire()
      observers.fire()
      expect(screen.getByTestId('conversation-interject-inline')).toBeInTheDocument()
      expect(screen.queryByTestId('conversation-interject-tray')).toBeNull()
    } finally {
      observers.restore()
    }
  })

  it('floats again once the window gives the conversation room', () => {
    const observers = recordResizeObservers()
    try {
      let room = 150
      layOut({ tray: 144, turn: 120, room: () => room })
      render(<AgentOutputPanel agent={agent} conversationId="conv-1" />)
      expect(screen.getByTestId('conversation-interject-inline')).toBeInTheDocument()

      // Enough to float (300 >= 240), though not once an inline tray's 152px is taken out of it.
      room = 300
      observers.fire()

      expect(screen.getByTestId('conversation-interject-tray')).toContainElement(
        screen.getByTestId('agent-question-q-1'),
      )
      expect(screen.queryByTestId('conversation-interject-inline')).toBeNull()
      expect(screen.getByTestId('conversation-tray-inset')).toHaveStyle({ height: '152px' })
    } finally {
      observers.restore()
    }
  })
})
