import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { Sidebar } from '@/components/layout/Sidebar'
import { CONVERSATION_DISPLAY_CAP } from '@/components/layout/AgentTree'
import { useConfigStore } from '@/store/configStore'

const projects = [
  {
    id: 'proj-a',
    name: 'Website',
    working_directory: 'C:/work/a',
    path_display: 'C:/work/a',
    directory_state: 'available',
    last_opened_at: null,
    last_seen_at: null,
    hop_budget: 20,
    turn_delivery_cap: 20,
    agent_budget: 10,
    token_budget: null,
    allow_agent_jobs: true,
    agents: [
      { id: 'agent-a', name: 'claude', color_index: 1, status: 'running', last_seen: null },
      { id: 'agent-b', name: 'codex', color_index: 3, status: 'idle', last_seen: null },
    ],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

let payload: ProjectConversations = { conversations: [], archived_count: 0 }
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: payload }) }
})

function conversation(overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id: 'conv-1',
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title: 'Investigate the flaky checkout test',
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-08T00:00:00Z',
    updated_at: '2026-08-08T00:00:00Z',
    ...overrides,
  }
}

function renderRail(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    activePage: 'overview',
    activeAgent: null,
    onOpenProject: vi.fn(),
    onOpenAgent: vi.fn(),
    onOpenConversation: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onOpenExisting: vi.fn(),
    onCreateProject: vi.fn(),
    ...overrides,
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    ...render(
      <QueryClientProvider client={client}>
        <Sidebar {...props} />
      </QueryClientProvider>,
    ),
    props,
  }
}

function expandClaude() {
  fireEvent.click(screen.getByTestId('agent-expander-proj-a-claude'))
}

describe('conversations as a navigable level', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    payload = { conversations: [], archived_count: 0 }
  })

  it('lists an agent’s conversations beneath it, newest first, labelled by title', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-new', title: 'Newest thread' }),
        conversation({ id: 'conv-old', title: 'Older thread' }),
      ],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const rows = screen.getByTestId('agent-conversations-proj-a-claude')
    expect(rows.textContent).toContain('Newest thread')
    expect(rows.textContent).toContain('Older thread')
    expect(rows.textContent?.indexOf('Newest thread')).toBeLessThan(
      rows.textContent?.indexOf('Older thread') ?? 0,
    )
  })

  it('never shows a conversation identifier as its label', () => {
    payload = {
      conversations: [conversation({ id: 'conv-a3f81b2c', title: null })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const row = screen.getByTestId('rail-conversation-conv-a3f81b2c')
    expect(row.textContent).toContain('New conversation')
    expect(row.textContent).not.toContain('conv-a3f81b2c')
  })

  it('expands without navigating, and the agent name still opens the agent', () => {
    payload = { conversations: [conversation()], archived_count: 0 }
    const { props } = renderRail()

    expandClaude()
    expect(props.onOpenAgent).not.toHaveBeenCalled()
    expect(screen.getByTestId('agent-conversations-proj-a-claude')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('rail-agent-proj-a-claude'))
    expect(props.onOpenAgent).toHaveBeenCalledWith('proj-a', 'claude')
  })

  it('opens a conversation from the rail', () => {
    payload = { conversations: [conversation({ id: 'conv-42' })], archived_count: 0 }
    const { props } = renderRail()
    expandClaude()

    fireEvent.click(screen.getByTestId('rail-conversation-conv-42'))
    expect(props.onOpenConversation).toHaveBeenCalledWith('proj-a', 'claude', 'conv-42')
  })

  it('groups each agent’s conversations under that agent only', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-claude', agent: 'claude', title: 'Claude thread' }),
        conversation({ id: 'conv-codex', agent: 'codex', title: 'Codex thread' }),
      ],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const rows = screen.getByTestId('agent-conversations-proj-a-claude')
    expect(rows.textContent).toContain('Claude thread')
    expect(rows.textContent).not.toContain('Codex thread')
  })

  it('caps the list and states how many are hidden, never dropping them silently', () => {
    payload = {
      conversations: Array.from({ length: CONVERSATION_DISPLAY_CAP + 3 }, (_, index) =>
        conversation({ id: `conv-${index}`, title: `Thread ${index}` }),
      ),
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    expect(screen.queryByTestId(`rail-conversation-conv-${CONVERSATION_DISPLAY_CAP}`)).toBeNull()
    const expander = screen.getByTestId('conversation-expander-proj-a-claude')
    expect(expander.textContent).toContain('Show 3 more')

    fireEvent.click(expander)
    expect(screen.getByTestId(`rail-conversation-conv-${CONVERSATION_DISPLAY_CAP}`)).toBeInTheDocument()
  })

  it('offers a way back once expanded', () => {
    // Shipped without this: the control vanished after expanding, so an agent with 40
    // conversations stayed 40 rows tall for the rest of the session.
    payload = {
      conversations: Array.from({ length: CONVERSATION_DISPLAY_CAP + 3 }, (_, index) =>
        conversation({ id: `conv-${index}`, title: `Thread ${index}` }),
      ),
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    fireEvent.click(screen.getByTestId('conversation-expander-proj-a-claude'))
    const collapse = screen.getByTestId('conversation-expander-proj-a-claude')
    expect(collapse.textContent).toContain('Show fewer')

    fireEvent.click(collapse)
    expect(screen.queryByTestId(`rail-conversation-conv-${CONVERSATION_DISPLAY_CAP}`)).toBeNull()
    expect(screen.getByTestId('conversation-expander-proj-a-claude').textContent).toContain(
      'Show 3 more',
    )
  })

  it('marks a waiting conversation distinctly from a running one', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-waiting', attention: 'waiting' }),
        conversation({ id: 'conv-running', attention: 'running' }),
        conversation({ id: 'conv-idle', attention: 'idle' }),
      ],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    expect(screen.getByTestId('rail-conversation-conv-waiting-attention')).toHaveAttribute(
      'title',
      'Waiting for you',
    )
    expect(screen.getByTestId('rail-conversation-conv-running-attention')).toHaveAttribute(
      'title',
      'Running',
    )
    expect(screen.queryByTestId('rail-conversation-conv-idle-attention')).toBeNull()
  })

  it('surfaces a waiting conversation on the agent row while the agent is collapsed', () => {
    payload = {
      conversations: [conversation({ id: 'conv-waiting', attention: 'waiting' })],
      archived_count: 0,
    }
    renderRail()

    // Collapsed by default — the blocked run must still be visible, or the attention state
    // only works for agents you already expanded.
    expect(screen.getByTestId('rail-agent-attention-proj-a-claude')).toBeInTheDocument()

    expandClaude()
    expect(screen.queryByTestId('rail-agent-attention-proj-a-claude')).toBeNull()
  })

  it('distinguishes a peer-created conversation', () => {
    payload = {
      conversations: [conversation({ id: 'conv-peer', origin: 'peer' })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    expect(screen.getByTestId('rail-conversation-conv-peer-origin')).toBeInTheDocument()
    expect(screen.getByTestId('rail-conversation-conv-peer')).toHaveAttribute('data-origin', 'peer')
  })

  it('persists agent expansion across remounts, per project', () => {
    payload = { conversations: [conversation()], archived_count: 0 }
    const first = renderRail()
    expandClaude()
    first.unmount()

    renderRail()
    expect(screen.getByTestId('agent-conversations-proj-a-claude')).toBeInTheDocument()
    expect(screen.queryByTestId('agent-conversations-proj-a-codex')).toBeNull()
  })

  it('says so when an expanded agent has no conversations', () => {
    renderRail()
    expandClaude()
    expect(screen.getByTestId('no-conversations-proj-a-claude')).toBeInTheDocument()
  })
})
