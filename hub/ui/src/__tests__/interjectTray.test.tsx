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
import { render, screen } from '@testing-library/react'
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
 *  between renders cannot drop them. */
const originalOffsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')
function layOut({ tray, turn }: { tray: number; turn: number }) {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) {
      if (this.classList?.contains('conversation-interject-tray-column')) return tray
      if (this.hasAttribute?.('data-turn-boundary')) return turn
      return 0
    },
  })
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
