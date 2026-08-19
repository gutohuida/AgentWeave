/**
 * A run of firings collapsed to one row — in both rail views.
 *
 * The marker made a firing identifiable; grouping stops a loop left running overnight from burying
 * the threads the operator typed. What collapsing must not hide is the point of these tests:
 * attention, and the conversation currently being read.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { Sidebar } from '@/components/layout/Sidebar'
import { selectProjectPanel, usePanelTabsStore } from '@/store/panelTabsStore'
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
    agents: [{ id: 'agent-a', name: 'claude', color_index: 1, status: 'idle', last_seen: null }],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

let payload: ProjectConversations = { conversations: [], archived_count: 0 }
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return { ...actual, useProjectConversations: () => ({ data: payload }) }
})

const SWEEP = { id: 'loop-7', label: 'nightly sweep' }

function conv(id: string, overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id,
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title: id,
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
    ...overrides,
  }
}

function firing(id: string, overrides: Partial<AgentConversation> = {}): AgentConversation {
  return conv(id, { origin: 'job', loop: SWEEP, ...overrides })
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
const toRecency = () => fireEvent.click(screen.getByTestId('rail-view-toggle'))

describe('consecutive firings collapse into one row', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    payload = { conversations: [], archived_count: 0 }
  })

  it('shows one row for a run, naming the loop and counting the firings', () => {
    payload = {
      conversations: [firing('f1'), firing('f2'), firing('f3'), conv('typed')],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const group = screen.getByTestId('rail-loop-group-f1')
    expect(group).toHaveTextContent('nightly sweep')
    expect(screen.getByTestId('rail-loop-group-f1-count')).toHaveTextContent('3')
    // Collapsed by default: the firings are not rows until asked for.
    expect(screen.queryByTestId('rail-conversation-f1')).toBeNull()
    // The thread the operator typed is untouched and still its own row.
    expect(screen.getByTestId('rail-conversation-typed')).toBeInTheDocument()
  })

  it('expands to the individual firings, which no longer repeat the loop name', () => {
    payload = { conversations: [firing('f1'), firing('f2')], archived_count: 0 }
    renderRail()
    expandClaude()

    fireEvent.click(screen.getByTestId('rail-loop-group-f1-expander'))

    expect(screen.getByTestId('rail-conversation-f1')).toBeInTheDocument()
    expect(screen.getByTestId('rail-conversation-f2')).toBeInTheDocument()
    // The group row says it once for all of them.
    expect(screen.queryByTestId('rail-conversation-f1-loop')).toBeNull()
  })

  it('opens a firing from inside the group', () => {
    payload = { conversations: [firing('f1'), firing('f2')], archived_count: 0 }
    const { props } = renderRail()
    expandClaude()
    fireEvent.click(screen.getByTestId('rail-loop-group-f1-expander'))

    fireEvent.click(screen.getByTestId('rail-conversation-f2'))

    expect(props.onOpenConversation).toHaveBeenCalledWith('proj-a', 'claude', 'f2')
  })

  it('opens the loop itself from the group row', () => {
    payload = { conversations: [firing('f1'), firing('f2')], archived_count: 0 }
    const { props } = renderRail()
    expandClaude()

    fireEvent.click(screen.getByTestId('rail-loop-group-f1-open'))

    const panel = selectProjectPanel(usePanelTabsStore.getState(), 'proj-a')
    expect(panel.activeTabId).toBe('loop:loop-7')
    expect(props.onOpenConversation).not.toHaveBeenCalled()
  })

  it('surfaces a firing waiting for the operator without being expanded', () => {
    // The whole reason the attention state exists. Collapsing must not bury it — the same
    // argument the agent row already makes for its own collapsed state.
    payload = {
      conversations: [firing('f1'), firing('f2', { attention: 'waiting' })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const dot = screen.getByTestId('rail-loop-group-f1-attention')
    expect(dot).toHaveAttribute('aria-label', 'A firing is waiting for you')
  })

  it('opens itself when it holds the conversation being read', () => {
    payload = { conversations: [firing('f1'), firing('f2')], archived_count: 0 }
    renderRail({ activeConversation: 'f2' })
    expandClaude()

    expect(screen.getByTestId('rail-conversation-f2')).toBeInTheDocument()
  })

  it('leaves a single firing as a plain row with its marker', () => {
    payload = { conversations: [conv('typed'), firing('f1')], archived_count: 0 }
    renderRail()
    expandClaude()

    expect(screen.queryByTestId('rail-loop-group-f1')).toBeNull()
    expect(screen.getByTestId('rail-conversation-f1-loop')).toHaveTextContent('nightly sweep')
  })

  it('groups in the recency view too, where firings interleave with typed threads', () => {
    payload = {
      conversations: [conv('typed-1'), firing('f1'), firing('f2'), conv('typed-2')],
      archived_count: 0,
    }
    renderRail()
    toRecency()

    expect(screen.getByTestId('recency-loop-group-f1-count')).toHaveTextContent('2')
    // Order is preserved — grouping never moves a conversation past another.
    const rail = screen.getByTestId('rail-recency-proj-a')
    const text = rail.textContent ?? ''
    expect(text.indexOf('typed-1')).toBeLessThan(text.indexOf('nightly sweep'))
    expect(text.indexOf('nightly sweep')).toBeLessThan(text.indexOf('typed-2'))
  })
})
