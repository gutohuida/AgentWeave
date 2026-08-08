import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { RECENCY_DISPLAY_CAP } from '@/components/layout/RecencyView'
import { Sidebar } from '@/components/layout/Sidebar'
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
      { id: 'agent-a', name: 'claude', color_index: 1, status: 'idle', last_seen: null },
      { id: 'agent-b', name: 'codex', color_index: 3, status: 'idle', last_seen: null },
    ],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

let openPayload: ProjectConversations = { conversations: [], archived_count: 0 }
let archivedPayload: ProjectConversations = { conversations: [], archived_count: 0 }

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return {
    ...actual,
    useProjectConversations: (projectId: string | null, lifecycle: string = 'open') => ({
      data: projectId === null ? undefined : lifecycle === 'archived' ? archivedPayload : openPayload,
    }),
  }
})

function conversation(overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id: 'conv-1',
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title: 'A thread',
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

const toggle = () => fireEvent.click(screen.getByTestId('rail-view-toggle'))

describe('the recency view', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    openPayload = { conversations: [], archived_count: 0 }
    archivedPayload = { conversations: [], archived_count: 0 }
  })

  it('is not the default — the agent tree is', () => {
    renderRail()
    expect(screen.getByTestId('rail-agent-proj-a-claude')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-recency-proj-a')).toBeNull()
  })

  it('replaces the tree when toggled, and lists conversations across agents newest first', () => {
    openPayload = {
      conversations: [
        conversation({ id: 'conv-newest', agent: 'codex', title: 'Newest, from codex' }),
        conversation({ id: 'conv-older', agent: 'claude', title: 'Older, from claude' }),
      ],
      archived_count: 0,
    }
    renderRail()
    toggle()

    const list = screen.getByTestId('rail-recency-proj-a')
    expect(screen.queryByTestId('rail-agent-proj-a-claude')).toBeNull()
    expect(list.textContent?.indexOf('Newest, from codex')).toBeLessThan(
      list.textContent?.indexOf('Older, from claude') ?? 0,
    )
  })

  it('carries each conversation’s agent colour at rest, with no hover needed', () => {
    openPayload = {
      conversations: [
        conversation({ id: 'conv-claude', agent: 'claude' }),
        conversation({ id: 'conv-codex', agent: 'codex' }),
      ],
      archived_count: 0,
    }
    renderRail()
    toggle()

    const claudeEdge = screen.getByTestId('recency-conversation-conv-claude-edge')
    const codexEdge = screen.getByTestId('recency-conversation-conv-codex-edge')
    expect(claudeEdge).toBeInTheDocument()
    expect(codexEdge).toBeInTheDocument()
    // Different agents, different colours — that is the whole point of the edge.
    expect(claudeEdge.getAttribute('style')).not.toEqual(codexEdge.getAttribute('style'))
  })

  it('shows the same attention indicator as the tree', () => {
    openPayload = {
      conversations: [conversation({ id: 'conv-waiting', attention: 'waiting' })],
      archived_count: 0,
    }
    renderRail()
    toggle()

    expect(screen.getByTestId('recency-conversation-conv-waiting-attention')).toHaveAttribute(
      'title',
      'Waiting for you',
    )
  })

  it('opens a conversation with its own agent, not the selected one', () => {
    openPayload = {
      conversations: [conversation({ id: 'conv-codex', agent: 'codex' })],
      archived_count: 0,
    }
    const { props } = renderRail()
    toggle()

    fireEvent.click(screen.getByTestId('recency-conversation-conv-codex'))
    expect(props.onOpenConversation).toHaveBeenCalledWith('proj-a', 'codex', 'conv-codex')
  })

  it('survives a reload', () => {
    const first = renderRail()
    toggle()
    first.unmount()

    renderRail()
    expect(screen.getByTestId('rail-recency-proj-a')).toBeInTheDocument()
  })

  it('hides archived conversations but says how many there are', () => {
    openPayload = { conversations: [conversation()], archived_count: 3 }
    archivedPayload = {
      conversations: [conversation({ id: 'conv-gone', title: 'Archived thread', lifecycle: 'archived' })],
      archived_count: 3,
    }
    renderRail()
    toggle()

    expect(screen.queryByTestId('recency-archived-conv-gone')).toBeNull()
    const control = screen.getByTestId('recency-show-archived-proj-a')
    expect(control.textContent).toContain('Show archived (3)')

    fireEvent.click(control)
    expect(screen.getByTestId('recency-archived-conv-gone')).toBeInTheDocument()
    expect(screen.getByTestId('recency-show-archived-proj-a').textContent).toContain('Hide archived')
  })

  it('offers no archive control when nothing is archived', () => {
    openPayload = { conversations: [conversation()], archived_count: 0 }
    renderRail()
    toggle()
    expect(screen.queryByTestId('recency-show-archived-proj-a')).toBeNull()
  })

  it('says so when the project has no conversations', () => {
    renderRail()
    toggle()
    expect(screen.getByTestId('recency-empty-proj-a')).toBeInTheDocument()
  })

  it('caps the project’s conversations and states how many are hidden', () => {
    openPayload = {
      conversations: Array.from({ length: RECENCY_DISPLAY_CAP + 4 }, (_, index) =>
        conversation({ id: `conv-${index}`, title: `Thread ${index}` }),
      ),
      archived_count: 0,
    }
    renderRail()
    toggle()

    expect(screen.getByTestId(`recency-conversation-conv-${RECENCY_DISPLAY_CAP - 1}`)).toBeInTheDocument()
    expect(screen.queryByTestId(`recency-conversation-conv-${RECENCY_DISPLAY_CAP}`)).toBeNull()
    expect(screen.getByTestId('recency-expander-proj-a').textContent).toContain('Show 4 more')
  })

  it('expands to the whole project list, and back again', () => {
    openPayload = {
      conversations: Array.from({ length: RECENCY_DISPLAY_CAP + 4 }, (_, index) =>
        conversation({ id: `conv-${index}`, title: `Thread ${index}` }),
      ),
      archived_count: 0,
    }
    renderRail()
    toggle()

    fireEvent.click(screen.getByTestId('recency-expander-proj-a'))
    expect(screen.getByTestId(`recency-conversation-conv-${RECENCY_DISPLAY_CAP + 3}`)).toBeInTheDocument()

    // The way back — the defect the operator found in the tree's version of this control.
    const back = screen.getByTestId('recency-expander-proj-a')
    expect(back.textContent).toContain('Show fewer')
    fireEvent.click(back)
    expect(screen.queryByTestId(`recency-conversation-conv-${RECENCY_DISPLAY_CAP}`)).toBeNull()
  })

  it('offers no expander when the project is under the cap', () => {
    openPayload = { conversations: [conversation()], archived_count: 0 }
    renderRail()
    toggle()
    expect(screen.queryByTestId('recency-expander-proj-a')).toBeNull()
  })
})
