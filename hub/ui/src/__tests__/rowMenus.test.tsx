import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentConversation, ProjectConversations } from '@/api/agentChat'
import { ApiError } from '@/api/client'
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
    agents: [{ id: 'agent-a', name: 'claude', color_index: 1, status: 'idle', last_seen: null }],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))
vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'claude', status: 'idle', message_count: 0, active_task_count: 0 }] }),
}))
// The dialog's *placement* is what section 7.4 is about; what it renders inside is
// AgentInfoTab's own business and is tested elsewhere.
vi.mock('@/components/agents/AgentInfoTab', () => ({
  AgentInfoTab: ({ agent }: { agent: { name: string } }) => (
    <div data-testid="agent-info-tab">{agent.name} settings body</div>
  ),
}))

let openPayload: ProjectConversations = { conversations: [], archived_count: 0, archived_by_agent: {} }
let archivedPayload: ProjectConversations = { conversations: [], archived_count: 0, archived_by_agent: {} }
vi.mock('@/api/projectBuilds', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/projectBuilds')>()
  return {
    ...actual,
    useBuildsOfProject: () => ({ data: [], isError: false, refetch: vi.fn() }),
    useDismissProjectBuild: () => ({ mutate: vi.fn() }),
  }
})
const rename = vi.fn()
const archive = vi.fn()
const unarchive = vi.fn()

vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  return {
    ...actual,
    useOperatorThreads: (_projectId: string, lifecycle: string = 'open', enabled = true) => ({
      data: !enabled ? undefined : lifecycle === 'archived' ? archivedPayload : openPayload,
      isError: false,
      refetch: vi.fn(),
    }),
    useRenameConversation: () => ({ mutate: rename }),
    useArchiveConversation: () => ({ mutate: archive }),
    useUnarchiveConversation: () => ({ mutate: unarchive }),
  }
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

describe('every navigation row exposes its actions through a visible menu', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    rename.mockReset()
    archive.mockReset()
    unarchive.mockReset()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
    openPayload = { conversations: [conversation()], archived_count: 0, archived_by_agent: {} }
    archivedPayload = { conversations: [], archived_count: 0, archived_by_agent: {} }
  })

  it('offers rename and archive on a conversation row', async () => {
    const user = userEvent.setup()
    renderRail()

    // The control is on the row itself, not behind a right-click with no visible affordance.
    const trigger = screen.getByTestId('rail-thread-conv-1-menu')
    await user.click(trigger)

    const items = (await screen.findAllByRole('menuitem')).map((item) => item.textContent ?? '')
    expect(items).toEqual(['Rename', 'Archive'])
  })

  it('is operable by keyboard alone, and returns focus to its trigger', async () => {
    const user = userEvent.setup()
    renderRail()

    const trigger = screen.getByTestId('rail-thread-conv-1-menu')
    trigger.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('menu')

    // Opened from the keyboard, focus lands on the first item.
    await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Rename' })).toHaveFocus())
    await user.keyboard('{ArrowDown}')
    await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Archive' })).toHaveFocus())

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('renames in place, and sends the new title', async () => {
    const user = userEvent.setup()
    renderRail()

    await user.click(screen.getByTestId('rail-thread-conv-1-menu'))
    await user.click(await screen.findByRole('menuitem', { name: 'Rename' }))

    const input = await screen.findByTestId('rail-thread-conv-1-rename')
    fireEvent.change(input, { target: { value: 'Checkout flake, day two' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(rename).toHaveBeenCalledWith(
      {
        projectId: 'proj-a',
        agent: 'claude',
        conversationId: 'conv-1',
        title: 'Checkout flake, day two',
      },
      expect.anything(),
    )
  })

  it('leaves the title alone when a rename is escaped', async () => {
    const user = userEvent.setup()
    renderRail()

    await user.click(screen.getByTestId('rail-thread-conv-1-menu'))
    await user.click(await screen.findByRole('menuitem', { name: 'Rename' }))

    const input = await screen.findByTestId('rail-thread-conv-1-rename')
    fireEvent.change(input, { target: { value: 'Never mind' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(rename).not.toHaveBeenCalled()
    expect(screen.getByTestId('rail-thread-conv-1')).toBeInTheDocument()
  })

  it('archives from the row, and states the Hub’s reason when it refuses', async () => {
    archive.mockImplementation((_vars, options) =>
      options?.onError?.(
        new ApiError(409, JSON.stringify({ detail: 'A run is still in progress' })),
      ),
    )
    const user = userEvent.setup()
    renderRail()

    await user.click(screen.getByTestId('rail-thread-conv-1-menu'))
    await user.click(await screen.findByRole('menuitem', { name: 'Archive' }))

    expect(archive).toHaveBeenCalledWith(
      { projectId: 'proj-a', agent: 'claude', conversationId: 'conv-1' },
      expect.anything(),
    )
    // Refusing is the design; refusing silently is not.
    expect(await screen.findByTestId('rail-thread-conv-1-error')).toHaveTextContent(
      'A run is still in progress',
    )
  })

  it('offers unarchive, not archive, on an archived row', async () => {
    openPayload = { conversations: [], archived_count: 1, archived_by_agent: { claude: 1 } }
    archivedPayload = {
      conversations: [conversation({ id: 'conv-gone', lifecycle: 'archived' })],
      archived_count: 1,
      archived_by_agent: { claude: 1 },
    }
    const user = userEvent.setup()
    renderRail()

    await user.click(screen.getByRole('button', { name: 'Show archived (1)' }))

    const trigger = await screen.findByTestId('rail-thread-archived-conv-gone-menu')
    await user.click(trigger)
    const items = (await screen.findAllByRole('menuitem')).map((item) => item.textContent ?? '')
    expect(items).toEqual(['Unarchive'])
  })

  it('never shows a conversation identifier as a label anywhere in the rail', async () => {
    openPayload = {
      conversations: [
        conversation({ id: 'conv-a3f81b2c', title: 'A named thread' }),
        conversation({ id: 'conv-77ce01ff', title: null }),
      ],
      archived_count: 0,
      archived_by_agent: {},
    }
    renderRail()

    const rail = screen.getByTestId('sidebar')
    expect(rail.textContent).toContain('A named thread')
    // A conversation with no title yet is labelled as new, never by its id.
    expect(rail.textContent).toContain('New conversation')
    expect(rail.textContent).not.toContain('conv-a3f81b2c')
    expect(rail.textContent).not.toContain('conv-77ce01ff')
  })
})
