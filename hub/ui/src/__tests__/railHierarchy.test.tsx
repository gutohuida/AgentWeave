import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { Sidebar } from '@/components/layout/Sidebar'
import { useConfigStore } from '@/store/configStore'

/* The rail's information hierarchy: project → its threads and builds.

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
  return {
    ...actual,
    useOperatorThreads: (_projectId: string, lifecycle = 'open') => ({
      data: lifecycle === 'open' ? payload : undefined,
      isError: false,
      refetch: vi.fn(),
    }),
  }
})
vi.mock('@/api/projectBuilds', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projectBuilds')>()
  return {
    ...actual,
    useBuildsOfProject: () => ({ data: [], isError: false, refetch: vi.fn() }),
    useDismissProjectBuild: () => ({ mutate: vi.fn() }),
  }
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
    onOpenProject: vi.fn(),
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

beforeEach(() => {
  cleanup()
  localStorage.clear()
  useConfigStore.setState({ selectedProjectId: 'proj-a' })
  payload = { conversations: [], archived_count: 0 }
  connectionState = 'open'
})

describe('one selection treatment across the rail levels', () => {
  it('grades every level of the open path, deepest last', () => {
    payload = { conversations: [conversation({ id: 'conv-open' })], archived_count: 0 }
    renderRail({ activeConversation: 'conv-open' })

    const project = screen.getByTestId('project-name-proj-a')
    const conv = screen.getByTestId('rail-thread-conv-open')

    // Both are on the open path and both say so — one treatment, not two.
    for (const row of [project, conv]) {
      expect(row).toHaveAttribute('data-active', 'true')
    }
    // And each declares which level it is, so the ladder in index.css can grade them.
    expect(project).toHaveAttribute('data-depth', 'project')
    expect(conv).toHaveAttribute('data-depth', 'conversation')
  })

  it('marks the conversation, not just its project', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-open', title: 'Open thread' }),
        conversation({ id: 'conv-other', title: 'Other thread' }),
      ],
      archived_count: 0,
    }
    renderRail({ activeConversation: 'conv-open' })

    expect(screen.getByTestId('rail-thread-conv-open')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('rail-thread-conv-open')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByTestId('rail-thread-conv-other')).toHaveAttribute('data-active', 'false')
  })

  it('draws no leading accent bar on any level', () => {
    // Removed at the operator's request 2026-08-19, reintroduced on project rows only, and
    // removed again here. Asserted so the next mock that proposes restoring it fails loudly
    // instead of quietly contradicting the comment that records the decision.
    payload = { conversations: [conversation({ id: 'conv-open' })], archived_count: 0 }
    const { container } = renderRail({ activeConversation: 'conv-open' })
    expect(screen.getByTestId('rail-thread-conv-open')).toBeInTheDocument()

    expect(container.querySelectorAll('.row-selection-indicator')).toHaveLength(0)
  })
})

describe('thread rows carry their recency in the tooltip', () => {
  const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
  const HOUR = 3_600_000

  it('names the profile on the row and keeps the age in the tooltip, the list being in recency order', () => {
    const at = ago(2 * HOUR)
    payload = { conversations: [conversation({ id: 'conv-1', updated_at: at, last_activity_at: at })], archived_count: 0 }
    renderRail()
    const row = screen.getByTestId('rail-thread-conv-1')
    expect(screen.getByTestId('rail-thread-conv-1-profile').textContent).toBe('claude')
    expect(screen.queryByTestId('rail-thread-conv-1-age')).toBeNull()
    expect(row.getAttribute('title')).toContain('last activity about 2 hours ago')
  })

  it('costs the tooltip its age rather than printing NaN', () => {
    payload = {
      conversations: [conversation({ id: 'conv-1', updated_at: 'not a timestamp', last_activity_at: null })],
      archived_count: 0,
    }
    renderRail()
    expect(screen.getByTestId('rail-thread-conv-1')).toBeInTheDocument()
    expect(screen.getByTestId('rail-thread-conv-1').getAttribute('title')).not.toContain('NaN')
  })
})

describe('the rail empty state', () => {
  it('offers exactly one way in from a project with no threads', () => {
    const onNewConversation = vi.fn()
    renderRail({ onNewConversation })

    const empty = screen.getByTestId('rail-threads-empty-proj-a')
    expect(empty.textContent).toContain('Start a thread')
    // Not two stacked copies of the same action.
    expect(screen.queryByRole('button', { name: 'New thread' })).toBeNull()

    fireEvent.click(empty)
    expect(onNewConversation).toHaveBeenCalledWith('proj-a', null)
  })

  it('gives the header action back once there is a list', () => {
    payload = { conversations: [conversation()], archived_count: 0 }
    renderRail()

    expect(screen.queryByTestId('rail-threads-empty-proj-a')).toBeNull()
    expect(screen.getByRole('button', { name: 'New thread' })).toBeInTheDocument()
  })
})

describe('the rail head carries the brand', () => {
  it('leads with the loop, then the name, then the live dot', () => {
    renderRail()
    const loop = screen.getByTestId('rail-brand-loop')
    const dot = screen.getByTestId('rail-live-dot')
    const name = screen.getByText('AgentWeave', { selector: '.aw-wordmark-name' })
    // The loop is decoration beside the name; the dot keeps its own accessible name.
    expect(loop).toHaveAttribute('aria-hidden', 'true')
    expect(loop.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(name.compareDocumentPosition(dot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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
