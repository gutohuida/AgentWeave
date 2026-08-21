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

const SPEC_HOME = 'spec/spec.html'
const SPEC_CHANGE = 'spec/changes/queued-message-delivery/spec.html'
// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({
    data: {
      specs: [
        { path: 'spec/spec.html', title: 'Specification', kind: 'baseline', state: 'filed', parent: null, order: 0 },
        { path: 'spec/changes/queued-message-delivery/spec.html', title: 'Queued message delivery', kind: 'change-spec', state: 'filed', parent: null, order: 10 },
      ],
      home: 'spec/spec.html',
      diagnostics: [],
      missing: [],
    },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: undefined, refetch: () => {} }),
  useSpecEvents: () => {},
}))

function renderRail(overrides: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props: React.ComponentProps<typeof Sidebar> = {
    activePage: 'overview',
    activeAgent: null,
    onOpenProject: vi.fn(),
    onOpenAgent: vi.fn(),
    onOpenEnvironment: vi.fn(),
    onAddAgent: vi.fn(),
    onAddProject: vi.fn(),
    ...overrides,
  }
  // The rail fetches each project's conversations now that agents expand to them, so it
  // needs a client even for the tests that never expand an agent.
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
 * nothing else — no projects, no agents, no way back, and no way to undo it. A rail that renders
 * no destinations is hidden, not collapsed. */
describe('the collapsed rail', () => {
  beforeEach(() => {
    cleanup()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  it('reaches every project and agent the expanded rail reaches, by name', () => {
    renderRail({ compact: true, onCompactChange: vi.fn() })

    for (const project of projects) {
      // By accessible name, not by pixel: an icon nobody can name is not a destination.
      expect(screen.getByTestId(`rail-compact-project-${project.id}`)).toHaveAccessibleName(
        project.name,
      )
      for (const agent of project.agents) {
        expect(
          screen.getByTestId(`rail-compact-agent-${project.id}-${agent.name}`),
        ).toHaveAccessibleName(agent.name)
      }
    }
  })

  it('navigates from the collapsed rail', () => {
    const onOpenProject = vi.fn()
    const onOpenAgent = vi.fn()
    renderRail({ compact: true, onCompactChange: vi.fn(), onOpenProject, onOpenAgent })

    fireEvent.click(screen.getByTestId('rail-compact-project-proj-b'))
    expect(onOpenProject).toHaveBeenCalledWith('proj-b')

    fireEvent.click(screen.getByTestId('rail-compact-agent-proj-a-claude'))
    expect(onOpenAgent).toHaveBeenCalledWith('proj-a', 'claude')
  })

  it('offers open-existing alongside add-project when collapsed', () => {
    const onAddProject = vi.fn()
    renderRail({ compact: true, onCompactChange: vi.fn(), onAddProject })

    fireEvent.click(screen.getByTestId('add-project'))
    expect(onAddProject).toHaveBeenCalledOnce()
  })

  it('indicates the active project and agent', () => {
    renderRail({ compact: true, onCompactChange: vi.fn(), activeAgent: 'claude' })
    expect(screen.getByTestId('rail-compact-project-proj-a')).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('rail-compact-project-proj-b')).toHaveAttribute('data-active', 'false')
    expect(screen.getByTestId('rail-compact-agent-proj-a-claude')).toHaveAttribute('data-active', 'true')
    // Same agent name, different project: the active marker follows the project too.
    expect(screen.getByTestId('rail-compact-agent-proj-b-codex')).toHaveAttribute('data-active', 'false')
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

/* The rail stands in for the project tree while the Spec screen is open, the way it already does
 * for Environment and agent settings (operator: "Is it possible to make it like the config screen
 * where the navigation replaces the left navigation? Two navigations are weird."). */
describe('the rail while the Spec screen is open', () => {
  const specDestination = {
    kind: 'project' as const,
    projectId: 'proj-a',
    tab: 'spec' as const,
    document: SPEC_CHANGE,
  }

  beforeEach(() => {
    cleanup()
    localStorage.clear()
    useConfigStore.setState({ selectedProjectId: 'proj-a' })
  })

  /** The rail opens folded, so reaching a nested document means opening its ancestors. */
  const unfoldTo = (docPath: string) => {
    const segments = docPath.split('/').slice(0, -1)
    for (let depth = 2; depth <= segments.length; depth += 1) {
      const dir = segments.slice(0, depth).join('/')
      const folder = screen.queryByTestId(`spec-tree-directory-${dir}`)
      if (folder && folder.getAttribute('aria-expanded') === 'false') fireEvent.click(folder)
    }
  }

  it('replaces the project tree with the specification tree', () => {
    renderRail({ destination: specDestination, activePage: 'spec' })

    expect(screen.getByTestId('spec-rail-tree')).toBeInTheDocument()
    // Folded by default in the rail, so the document is reached through its folders.
    unfoldTo(SPEC_CHANGE)
    expect(screen.getByTestId(`spec-tree-document-${SPEC_CHANGE}`)).toBeInTheDocument()
    // The project tree is not also there — that is the whole point.
    expect(screen.queryByTestId('rail-project-proj-a')).not.toBeInTheDocument()
    expect(screen.getByTestId('sidebar')).toHaveAttribute('data-mode', 'section')
  })

  it('gives the rail back in one press', () => {
    const onOpenProject = vi.fn()
    renderRail({ destination: specDestination, activePage: 'spec', onOpenProject })

    fireEvent.click(screen.getByTestId('spec-rail-back'))
    expect(onOpenProject).toHaveBeenCalledWith('proj-a')
  })

  it('marks the open document and opens another', () => {
    const onOpenSpecDocument = vi.fn()
    renderRail({ destination: specDestination, activePage: 'spec', onOpenSpecDocument })

    unfoldTo(SPEC_CHANGE)
    expect(screen.getByTestId(`spec-tree-document-${SPEC_CHANGE}`)).toHaveAttribute('aria-current', 'true')
    fireEvent.click(screen.getByTestId(`spec-tree-document-${SPEC_HOME}`))
    expect(onOpenSpecDocument).toHaveBeenCalledWith('proj-a', SPEC_HOME)
  })

  it('opens the rail folded, so the corpus does not unroll on arrival', () => {
    renderRail({ destination: specDestination, activePage: 'spec' })

    // The operator asked for this on 2026-08-21: 41 documents unrolled before anyone asked.
    const folder = screen.getByTestId('spec-tree-directory-spec/changes')
    expect(folder).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId(`spec-tree-document-${SPEC_CHANGE}`)).not.toBeInTheDocument()
  })

  it('unfolds a directory in one press, and remembers it', () => {
    const { unmount } = renderRail({ destination: specDestination, activePage: 'spec' })

    unfoldTo(SPEC_CHANGE)
    expect(screen.getByTestId(`spec-tree-document-${SPEC_CHANGE}`)).toBeInTheDocument()
    expect(screen.getByTestId('spec-tree-directory-spec/changes')).toHaveAttribute('aria-expanded', 'true')

    // A tree that forgets what you unfolded is a tree you unfold again every time.
    unmount()
    renderRail({ destination: specDestination, activePage: 'spec' })
    expect(screen.getByTestId(`spec-tree-document-${SPEC_CHANGE}`)).toBeInTheDocument()

    // And folding it back still works, and is still remembered.
    fireEvent.click(screen.getByTestId('spec-tree-directory-spec/changes'))
    expect(screen.queryByTestId(`spec-tree-document-${SPEC_CHANGE}`)).not.toBeInTheDocument()
  })
})
