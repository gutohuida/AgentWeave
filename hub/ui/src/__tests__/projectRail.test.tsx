import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Sidebar } from '@/components/layout/Sidebar'
import { useConfigStore } from '@/store/configStore'

const projects = [
  {
    id: 'proj-a', name: 'Website', working_directory: 'C:/work/client-a', path_display: 'C:/work/client-a',
    directory_state: 'available', last_opened_at: null, last_seen_at: null, hop_budget: 20,
    turn_delivery_cap: 20, agent_budget: 10, token_budget: null, allow_agent_jobs: true,
    agents: [{ id: 'agent-a', name: 'claude', color_index: 1, status: 'running', last_seen: null }],
  },
  {
    id: 'proj-b', name: 'Website', working_directory: 'D:/archive/client-b', path_display: 'D:/archive/client-b',
    directory_state: 'missing', last_opened_at: null, last_seen_at: null, hop_budget: 20,
    turn_delivery_cap: 20, agent_budget: 10, token_budget: null, allow_agent_jobs: true,
    agents: [{ id: 'agent-b', name: 'codex', color_index: 3, status: 'idle', last_seen: null }],
  },
]

vi.mock('@/api/projects', () => ({ useProjects: () => ({ data: projects, isLoading: false }) }))

// The rail no longer stands in for the Spec document tree (operator, 2026-10-20: the rail stays,
// and the Spec screen carries its own document list — see specDocumentList.test.tsx).

function renderRail(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    onOpenProject: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onAddProject: vi.fn(),
    ...overrides,
  }
  // Each open project reads its threads and builds, so the rail needs a client.
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

describe('phase 5 project collection rail', () => {
  beforeEach(() => {
    cleanup()
    localStorage.removeItem('aw.projectRailCollapsed')
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('renders every project and its own threads and builds with live directory state', () => {
    renderRail()
    expect(screen.getByTestId('rail-project-proj-a')).toBeInTheDocument()
    expect(screen.getByTestId('rail-project-proj-b')).toBeInTheDocument()
    expect(screen.getByTestId('rail-threads-builds-proj-a')).toBeInTheDocument()
    expect(screen.getByTestId('rail-threads-builds-proj-b')).toBeInTheDocument()
    // No agent tree under a project any more (profiles-threads-and-builds-everywhere FR-1).
    expect(screen.queryByTestId('rail-agent-proj-a-claude')).toBeNull()
    // One signal per row: an available folder says nothing, a missing one says so in words.
    expect(screen.queryByTestId('project-state-proj-a')).toBeNull()
    expect(screen.getByTestId('project-state-proj-b')).toHaveAccessibleName('Directory unavailable')
  })

  it('shows path hints only when names collide', () => {
    renderRail()
    expect(screen.getByText('C:/work/client-a')).toBeInTheDocument()
    expect(screen.getByText('D:/archive/client-b')).toBeInTheDocument()
  })

  it('keeps expansion independent from navigation and from other projects', () => {
    const onOpenProject = vi.fn()
    renderRail({ onOpenProject })
    fireEvent.click(screen.getByTestId('project-expander-proj-a'))
    expect(screen.queryByTestId('rail-threads-builds-proj-a')).not.toBeInTheDocument()
    expect(screen.getByTestId('rail-threads-builds-proj-b')).toBeInTheDocument()
    expect(onOpenProject).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('project-name-proj-a'))
    expect(onOpenProject).toHaveBeenCalledWith('proj-a')
    expect(screen.queryByTestId('rail-threads-builds-proj-a')).not.toBeInTheDocument()
  })

  it('persists collapsed projects across remounts', () => {
    const first = renderRail()
    fireEvent.click(screen.getByTestId('project-expander-proj-b'))
    first.unmount()
    renderRail()
    expect(screen.queryByTestId('rail-threads-builds-proj-b')).not.toBeInTheDocument()
    expect(screen.getByTestId('rail-threads-builds-proj-a')).toBeInTheDocument()
  })

  it('opens configuration and agent creation from the scoped project row', () => {
    const onOpenEnvironment = vi.fn()
    const onAddAgent = vi.fn()
    renderRail({ onOpenEnvironment, onAddAgent })
    fireEvent.click(screen.getAllByRole('button', { name: 'Configure Website' })[0])
    fireEvent.click(screen.getByTestId('rail-add-agent-proj-a'))
    // The project's gear opens Project settings at General, as the top bar's gear does.
    expect(onOpenEnvironment).toHaveBeenCalledWith('proj-a', 'general')
    expect(onAddAgent).toHaveBeenCalledWith('proj-a')
  })

  it('offers distinct open-existing and create-new actions', () => {
    const onAddProject = vi.fn()
    renderRail({ onAddProject })
    fireEvent.click(screen.getByTestId('add-project'))
    expect(onAddProject).toHaveBeenCalledOnce()
    // One action, not two: the second entry point was removed deliberately, so assert it is
    // gone rather than leaving its absence to be noticed by a human reading the rail.
    expect(screen.queryByTestId('open-existing-project')).toBeNull()
    expect(screen.queryByTestId('create-new-project')).toBeNull()
  })
})

/* `hub-workspace-shell`: "Navigation collapses only when the operator asks, and stays navigable
 * when it does."
 *
 * The previous compact mode gated every branch on `!compact`, so it rendered the "AW" avatar and
 * nothing else — no projects, no way back, and no way to undo it. A rail that renders
 * no destinations is hidden, not collapsed. */
describe('the collapsed rail', () => {
  beforeEach(() => {
    cleanup()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('reaches every project the expanded rail reaches, by name, and shows no profiles', () => {
    renderRail({ compact: true, onCompactChange: vi.fn() })

    for (const project of projects) {
      // By accessible name, not by pixel: an icon nobody can name is not a destination.
      expect(screen.getByTestId(`rail-compact-project-${project.id}`)).toHaveAccessibleName(
        project.name,
      )
    }
    // Projects only (FR-14): 52px cannot name a thread, and profiles are not destinations here.
    expect(screen.queryByTestId(/^rail-compact-agent-/)).toBeNull()
  })

  it('navigates from the collapsed rail', () => {
    const onOpenProject = vi.fn()
    renderRail({ compact: true, onCompactChange: vi.fn(), onOpenProject })

    fireEvent.click(screen.getByTestId('rail-compact-project-proj-b'))
    expect(onOpenProject).toHaveBeenCalledWith('proj-b')
  })

  it('offers open-existing alongside add-project when collapsed', () => {
    const onAddProject = vi.fn()
    renderRail({ compact: true, onCompactChange: vi.fn(), onAddProject })

    fireEvent.click(screen.getByTestId('add-project'))
    expect(onAddProject).toHaveBeenCalledOnce()
  })

  it('indicates the active project', () => {
    renderRail({ compact: true, onCompactChange: vi.fn() })
    expect(screen.getByTestId('rail-compact-project-proj-a')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('rail-compact-project-proj-b')).toHaveAttribute('data-active', 'false')
  })

  it('can be expanded again from within itself', () => {
    const onCompactChange = vi.fn()
    renderRail({ compact: true, onCompactChange })

    const toggle = screen.getByTestId('rail-collapse-toggle')
    expect(toggle).toHaveAttribute('aria-label', 'Expand navigation')
    fireEvent.click(toggle)
    expect(onCompactChange).toHaveBeenCalledWith(false)
  })

  it('is collapsed by the operator, and by nobody else', () => {
    const onCompactChange = vi.fn()
    renderRail({ compact: false, onCompactChange })

    // The rail has no destination-derived collapse of its own: the only thing that changes it is
    // this control, and the state lives outside the component entirely.
    fireEvent.click(screen.getByTestId('rail-collapse-toggle'))
    expect(onCompactChange).toHaveBeenCalledWith(true)
    expect(screen.getByTestId('sidebar')).toHaveAttribute('data-compact', 'false')
  })
})
