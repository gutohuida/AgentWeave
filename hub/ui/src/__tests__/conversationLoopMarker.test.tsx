/**
 * A conversation the operator never started says which loop produced it.
 *
 * A loop firing opens a *new* conversation every time, so the rail fills with threads nobody
 * typed. Measured on the trial Hub 2026-08-19: one agent, 20 conversations, 11 of them firings
 * across 5 loops, interleaved by recency with the 9 the operator started — and nothing on the row
 * distinguished them.
 *
 * The marker deliberately links into the *existing* `loop:<id>` drill-down rather than adding a
 * third loop surface — the rejected alternative was another expandable level in this rail
 * (design D2: "open on the right" must not mean two things).
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

function conversation(overrides: Partial<AgentConversation> = {}): AgentConversation {
  return {
    id: 'conv-1',
    agent: 'claude',
    provider_session_id: null,
    lifecycle: 'open',
    title: 'Swept the queue',
    title_set_by_operator: false,
    origin: 'operator',
    attention: 'idle',
    created_at: '2026-08-19T00:00:00Z',
    updated_at: '2026-08-19T00:00:00Z',
    ...overrides,
  }
}

function renderRail() {
  const props: React.ComponentProps<typeof Sidebar> = {
    activePage: 'overview',
    activeAgent: null,
    onOpenProject: vi.fn(),
    onOpenAgent: vi.fn(),
    onOpenConversation: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onAddProject: vi.fn(),
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

describe('a loop firing names its loop on the conversation row', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    usePanelTabsStore.setState({ projects: {} })
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    payload = { conversations: [], archived_count: 0 }
  })

  it('shows the loop’s name on a conversation a firing created', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-fired', origin: 'job', loop: { id: 'loop-7', label: 'nightly sweep' } }),
      ],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    const marker = screen.getByTestId('rail-conversation-conv-fired-loop')
    expect(marker.textContent).toContain('nightly sweep')
    expect(marker.getAttribute('data-loop-id')).toBe('loop-7')
  })

  it('shows nothing for a plain scheduled job, which has the same origin and no loop', () => {
    payload = {
      conversations: [conversation({ id: 'conv-job', origin: 'job', loop: null })],
      archived_count: 0,
    }
    renderRail()
    expandClaude()

    expect(screen.queryByTestId('rail-conversation-conv-job-loop')).toBeNull()
  })

  it('shows nothing on a conversation the operator started', () => {
    payload = { conversations: [conversation({ id: 'conv-typed' })], archived_count: 0 }
    renderRail()
    expandClaude()

    expect(screen.queryByTestId('rail-conversation-conv-typed-loop')).toBeNull()
  })

  it('opens the loop’s existing drill-down tab, without opening the conversation', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-fired', origin: 'job', loop: { id: 'loop-7', label: 'nightly sweep' } }),
      ],
      archived_count: 0,
    }
    const { props } = renderRail()
    expandClaude()

    fireEvent.click(screen.getByTestId('rail-conversation-conv-fired-loop'))

    const panel = selectProjectPanel(usePanelTabsStore.getState(), 'proj-a')
    expect(panel.tabs.map((tab) => tab.id)).toContain('loop:loop-7')
    expect(panel.activeTabId).toBe('loop:loop-7')
    expect(panel.isOpen).toBe(true)
    // The marker is its own destination — clicking it must not also navigate the row.
    expect(props.onOpenConversation).not.toHaveBeenCalled()
  })

  it('marks the row in the recency view too, where firings interleave with typed threads', () => {
    payload = {
      conversations: [
        conversation({ id: 'conv-fired', origin: 'job', loop: { id: 'loop-7', label: 'nightly sweep' } }),
        conversation({ id: 'conv-typed' }),
      ],
      archived_count: 0,
    }
    renderRail()
    fireEvent.click(screen.getByTestId('rail-view-toggle'))

    expect(screen.getByTestId('recency-conversation-conv-fired-loop').textContent).toContain(
      'nightly sweep',
    )
    expect(screen.queryByTestId('recency-conversation-conv-typed-loop')).toBeNull()
  })
})
