import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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

function renderRail(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    activePage: 'overview',
    activeAgent: null,
    onOpenProject: vi.fn(),
    onOpenAgent: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onOpenExisting: vi.fn(),
    onCreateProject: vi.fn(),
    ...overrides,
  }
  return { ...render(<Sidebar {...props} />), props }
}

describe('phase 5 project collection rail', () => {
  beforeEach(() => {
    cleanup()
    localStorage.removeItem('aw.projectRailCollapsed')
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('renders every project and its own agents with live directory state', () => {
    renderRail()
    expect(screen.getByTestId('rail-project-proj-a')).toBeInTheDocument()
    expect(screen.getByTestId('rail-project-proj-b')).toBeInTheDocument()
    expect(screen.getByTestId('rail-agent-proj-a-claude')).toBeInTheDocument()
    expect(screen.getByTestId('rail-agent-proj-b-codex')).toBeInTheDocument()
    expect(screen.getByTestId('project-state-proj-a')).toHaveAttribute('title', 'available')
    expect(screen.getByTestId('project-state-proj-b')).toHaveAttribute('title', 'missing')
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
    expect(screen.queryByTestId('rail-agent-proj-a-claude')).not.toBeInTheDocument()
    expect(screen.getByTestId('rail-agent-proj-b-codex')).toBeInTheDocument()
    expect(onOpenProject).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('project-name-proj-a'))
    expect(onOpenProject).toHaveBeenCalledWith('proj-a')
    expect(screen.queryByTestId('rail-agent-proj-a-claude')).not.toBeInTheDocument()
  })

  it('persists collapsed projects across remounts', () => {
    const first = renderRail()
    fireEvent.click(screen.getByTestId('project-expander-proj-b'))
    first.unmount()
    renderRail()
    expect(screen.queryByTestId('rail-agent-proj-b-codex')).not.toBeInTheDocument()
    expect(screen.getByTestId('rail-agent-proj-a-claude')).toBeInTheDocument()
  })

  it('opens configuration and agent creation from the scoped project row', () => {
    const onOpenEnvironment = vi.fn()
    const onAddAgent = vi.fn()
    renderRail({ onOpenEnvironment, onAddAgent })
    fireEvent.click(screen.getAllByRole('button', { name: 'Configure Website' })[0])
    fireEvent.click(screen.getByTestId('rail-add-agent-proj-a'))
    expect(onOpenEnvironment).toHaveBeenCalledWith('proj-a', 'quality')
    expect(onAddAgent).toHaveBeenCalledWith('proj-a')
  })

  it('derives section mode from the environment destination and returns in one action', () => {
    const onOpenProject = vi.fn()
    const onOpenEnvironment = vi.fn()
    renderRail({
      destination: { kind: 'project', projectId: 'proj-a', tab: 'environment', environmentSection: 'runners' },
      activePage: 'runners',
      onOpenProject,
      onOpenEnvironment,
    })
    expect(screen.getByTestId('sidebar')).toHaveAttribute('data-mode', 'section')
    expect(screen.getByTestId('environment-section-runners')).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByTestId('environment-section-settings'))
    fireEvent.click(screen.getByTestId('rail-section-back'))
    expect(onOpenEnvironment).toHaveBeenCalledWith('proj-a', 'settings')
    expect(onOpenProject).toHaveBeenCalledWith('proj-a')
  })

  it('offers distinct open-existing and create-new actions', () => {
    const onOpenExisting = vi.fn()
    const onCreateProject = vi.fn()
    renderRail({ onOpenExisting, onCreateProject })
    fireEvent.click(screen.getByTestId('open-existing-project'))
    fireEvent.click(screen.getByTestId('create-new-project'))
    expect(onOpenExisting).toHaveBeenCalledOnce()
    expect(onCreateProject).toHaveBeenCalledOnce()
  })
})
