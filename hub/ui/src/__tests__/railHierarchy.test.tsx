import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { Sidebar } from '@/components/layout/Sidebar'
import { useConfigStore } from '@/store/configStore'

/* The rail's information hierarchy: project → agent → conversation.
 *
 * The defect this file locks: the selection indicator was rendered on *project* rows and nowhere
 * else, so the outermost and least specific thing was marked most strongly while the conversation
 * being read carried nothing at all — and the indicator itself was the leading accent bar the
 * operator had removed on 2026-08-19, contradicting the comment in index.css that records the
 * removal.
 *
 * These tests assert the structure the CSS ladder hangs off (`data-depth`) rather than computed
 * styles: jsdom does not load index.css, so a test that read `background` here would pass on an
 * empty string and prove nothing. The attribute is the contract between these components and the
 * `.row-item[data-active][data-depth]` rules. */

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
    agents: [{ id: 'agent-a', name: 'claude', color_index: 1, status: 'idle', last_seen: null }],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

let payload: ProjectConversations = { conversations: [], archived_count: 0 }
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: payload }) }
})

let connectionState = 'open'
vi.mock('@/hooks/useSSE', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/useSSE')>()
  return { ...actual, useSSEConnectionState: () => connectionState }
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
    onNewConversation: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onAddProject: vi.fn(),
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

const expandClaude = () => fireEvent.click(screen.getByTestId('agent-expander-proj-a-claude'))

beforeEach(() => {
  cleanup()
  localStorage.clear()
  useConfigStore.setState({ selectedProjectId: 'proj-a' })
  payload = { conversations: [], archived_count: 0 }
  connectionState = 'open'
})

describe('one selection treatment across the three rail levels', () => {
  it('grades every level of the open path, deepest last', () => {
    payload = { conversations: [conversation({ id: 'conv-open' })], archived_count: 0 }
    renderRail({ activeAgent: 'claude', activeConversation: 'conv-open' })
    expandClaude()

    const project = screen.getByTestId('project-name-proj-a')
    const agent = screen.getByTestId('rail-agent-proj-a-claude')
    const conv = screen.getByTestId('rail-conversation-conv-open')

    // All three are on the open path and all three say so — one treatment, not three.
    for (const row of [project, agent, conv]) {
      expect(row).toHaveAttribute('data-active', 'true')
    }
    // And each declares which level it is, so the ladder in index.css can grade them.
    expect(project).toHaveAttribute('data-depth', 'project')
    expect(agent).toHaveAttribute('data-depth', 'agent')
    expect(conv).toHaveAttribute('data-depth', 'conversation')
  })

  it('marks the conversation, not just its ancestors', () => {
    // The inversion, stated as an assertion: before this change the conversation row carried
    // nothing that distinguished it from its five neighbours.
    payload = {
      conversations: [
        conversation({ id: 'conv-open', title: 'Open thread' }),
        conversation({ id: 'conv-other', title: 'Other thread' }),
      ],
      archived_count: 0,
    }
    renderRail({ activeAgent: 'claude', activeConversation: 'conv-open' })
    expandClaude()

    expect(screen.getByTestId('rail-conversation-conv-open')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('rail-conversation-conv-open')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('rail-conversation-conv-other')).toHaveAttribute('data-active', 'false')
  })

  it('draws no leading accent bar on any level', () => {
    // Removed at the operator's request 2026-08-19, reintroduced on project rows only, and
    // removed again here. Asserted so the next mock that proposes restoring it fails loudly
    // instead of quietly contradicting the comment that records the decision.
    payload = { conversations: [conversation({ id: 'conv-open' })], archived_count: 0 }
    const { container } = renderRail({ activeAgent: 'claude', activeConversation: 'conv-open' })
    expandClaude()

    expect(container.querySelectorAll('.row-selection-indicator')).toHaveLength(0)
  })

  it('leaves flat lists on the undepthed default', () => {
    // Environment sections are one level, not three. They must not acquire the conversation's
    // fill by accident, so they carry no `data-depth` at all.
    renderRail({
      destination: {
        kind: 'project',
        projectId: 'proj-a',
        tab: 'environment',
        environmentSection: 'runners',
      },
      activePage: 'runners',
    })
    const section = screen.getByTestId('environment-section-runners')
    expect(section).toHaveAttribute('data-active', 'true')
    expect(section).not.toHaveAttribute('data-depth')
  })
})

describe('conversation rows carry their recency', () => {
  /* Ages are expressed as offsets from the real clock rather than through fake timers: freezing
     time under React's renderer buys nothing here, and every row below is titled `null` on
     purpose — five threads all labelled "New conversation" is the case with no ordering cue at
     all, which is the defect. */
  const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
  const MINUTE = 60_000
  const HOUR = 60 * MINUTE
  const DAY = 24 * HOUR

  it('shows a compact age on every conversation row', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-now', title: null, updated_at: ago(30 * 1000) }),
        conversation({ id: 'conv-min', title: null, updated_at: ago(7 * MINUTE) }),
        conversation({ id: 'conv-hour', title: null, updated_at: ago(3 * HOUR) }),
        conversation({ id: 'conv-day', title: null, updated_at: ago(3 * DAY) }),
        conversation({ id: 'conv-week', title: null, updated_at: ago(14 * DAY) }),
      ],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    expect(screen.getByTestId('rail-conversation-conv-now-age').textContent).toBe('now')
    expect(screen.getByTestId('rail-conversation-conv-min-age').textContent).toBe('7m')
    expect(screen.getByTestId('rail-conversation-conv-hour-age').textContent).toBe('3h')
    expect(screen.getByTestId('rail-conversation-conv-day-age').textContent).toBe('3d')
    expect(screen.getByTestId('rail-conversation-conv-week-age').textContent).toBe('2w')
  })

  it('floors the age, so a row never claims to be newer than it is', () => {
    payload = {
      conversations: [conversation({ id: 'conv-1', updated_at: ago(HOUR + 59 * MINUTE) })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()
    expect(screen.getByTestId('rail-conversation-conv-1-age').textContent).toBe('1h')
  })

  it('carries the age into the recency view, whose whole purpose is recency', () => {
    payload = {
      conversations: [conversation({ id: 'conv-1', updated_at: ago(2 * HOUR) })],
      archived_count: 0,
    }
    renderRail()
    fireEvent.click(screen.getByTestId('rail-view-toggle'))
    expect(screen.getByTestId('recency-conversation-conv-1-age').textContent).toBe('2h')
  })

  it('costs the row its age rather than printing NaN', () => {
    payload = {
      conversations: [conversation({ id: 'conv-1', updated_at: 'not a timestamp' })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()
    expect(screen.getByTestId('rail-conversation-conv-1')).toBeInTheDocument()
    expect(screen.queryByTestId('rail-conversation-conv-1-age')).toBeNull()
  })
})

describe('the rail empty state', () => {
  it('offers the one action available from an empty agent branch', () => {
    const onNewConversation = vi.fn()
    renderRail({ onNewConversation })
    expandClaude()

    const empty = screen.getByTestId('no-conversations-proj-a-claude')
    expect(empty).toHaveClass('rail-empty')
    expect(empty.textContent).toContain('No conversations yet')

    fireEvent.click(screen.getByTestId('agent-new-conversation-proj-a-claude'))
    expect(onNewConversation).toHaveBeenCalledWith('proj-a', 'claude')
  })

  it('offers exactly one way in from an empty recency view', () => {
    const onNewConversation = vi.fn()
    renderRail({ onNewConversation })
    fireEvent.click(screen.getByTestId('rail-view-toggle'))

    expect(screen.getByTestId(`recency-empty-proj-a`)).toHaveClass('rail-empty')
    // Not two stacked copies of the same action.
    expect(screen.getAllByTestId('recency-new-conversation-proj-a')).toHaveLength(1)

    fireEvent.click(screen.getByTestId('recency-new-conversation-proj-a'))
    expect(onNewConversation).toHaveBeenCalledWith('proj-a', null)
  })

  it('gives the standalone action back once there is a list', () => {
    payload = { conversations: [conversation()], archived_count: 0 }
    renderRail()
    fireEvent.click(screen.getByTestId('rail-view-toggle'))

    expect(screen.queryByTestId('recency-empty-proj-a')).toBeNull()
    expect(screen.getByTestId('recency-new-conversation-proj-a')).toBeInTheDocument()
  })
})

describe('the live dot reports the Hub stream', () => {
  it('is bound to a real state and names it', () => {
    renderRail()
    const dot = screen.getByTestId('rail-live-dot')
    expect(dot).toHaveAttribute('data-state', 'open')
    expect(dot).toHaveAccessibleName('Live — receiving updates from the Hub')
    // Never decoration: an unnamed, unbound, permanently-green dot is what this replaced.
    expect(dot).not.toHaveAttribute('aria-hidden')
  })

  it('follows the connection rather than sitting green', () => {
    connectionState = 'reconnecting'
    renderRail()
    expect(screen.getByTestId('rail-live-dot')).toHaveAttribute('data-state', 'reconnecting')
    cleanup()

    // `closed` is deliberately not an error state — nothing subscribed is not a fault.
    connectionState = 'closed'
    renderRail()
    const dot = screen.getByTestId('rail-live-dot')
    expect(dot).toHaveAttribute('data-state', 'closed')
    expect(dot).toHaveAccessibleName('Not connected to the Hub')
  })
})
