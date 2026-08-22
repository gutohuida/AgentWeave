import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

// Stub useSSE so it doesn't try to connect. The module is mocked globally for
// the test file — we just need to confirm the App's tree wiring is right.
vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

// Real network calls must never escape a mounted-App test — App.tsx's real,
// unmocked hooks (useAgents, useProjects, etc.) would otherwise fire genuine
// fetch() requests and produce unhandled rejections against a fake host.
vi.stubGlobal(
  'fetch',
  vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
)

vi.mock('@/api/projects', () => ({
  useProjects: () => ({
    data: [{
      id: 'proj-test', name: 'AgentWeave', working_directory: 'C:/work/AgentWeave',
      path_display: 'C:/work/AgentWeave', directory_state: 'available', last_opened_at: null,
      last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
      token_budget: null, allow_agent_jobs: true,
      agents: [
        { id: 'agent-claude', name: 'claude', color_index: 2, status: 'idle', last_seen: null },
        { id: 'agent-codex', name: 'codex', color_index: 4, status: 'idle', last_seen: null },
      ],
    }, {
      id: 'proj-other', name: 'Client work', working_directory: 'C:/work/client',
      path_display: 'C:/work/client', directory_state: 'available', last_opened_at: null,
      last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
      token_budget: null, allow_agent_jobs: true, agents: [],
    }],
    isLoading: false,
  }),
  fetchProjectSummaries: vi.fn(async () => [{ id: 'proj-test' }]),
  useOpenProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useCreateProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useUpdateProjectSettings: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRelocateProject: () => ({ mutate: vi.fn(), error: null, isPending: false }),
}))
vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [
      { name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2 },
      { name: 'codex', status: 'idle', message_count: 0, active_task_count: 0, color_index: 4 },
    ],
    isLoading: false,
  }),
}))

// Stub every page component with a marker div that includes the page id in
// its testid. This lets us assert which page is mounted without depending
// on the real components' data fetching.
vi.mock('@/components/overview/OverviewPage', () => ({
  OverviewPage: ({ onNavigate }: { onNavigate?: (p: string) => void }) => (
    <div data-testid="page-overview">
      <button onClick={() => onNavigate?.('tasks')}>go to tasks</button>
      <button onClick={() => onNavigate?.('questions')}>Answer</button>
    </div>
  ),
}))
vi.mock('@/components/tasks/TasksBoard', () => ({
  TasksBoard: () => <div data-testid="page-tasks" />,
}))
vi.mock('@/components/tasks/DependencyBoardView', () => ({
  DependencyBoardView: () => <div data-testid="page-tasks-dependencies" />,
}))
// There is no Spec page and no Spec tab any more — a specification is opened from the composer's
// Spec pill, in the conversation the operator is already in. Mocked so the conversation view's
// inventory query never reaches the network.
// Partial mock: `importOriginal` keeps every export this file does not override real, so
// adding one to `@/api/spec` does not break a test that never used it. The whole-module form
// this replaced failed the moment the module grew `useSpecDocuments`.
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({
    data: { specs: [{ path: 'spec/spec.html' }], home: 'spec/spec.html', diagnostics: [], missing: [] },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: undefined, refetch: () => {} }),
  useSpecEvents: () => {},
}))
vi.mock('@/components/jobs/JobsPage', () => ({
  JobsPage: () => <div data-testid="page-jobs" />,
}))
vi.mock('@/components/questions/QuestionsPanel', () => ({
  QuestionsPanel: () => <div data-testid="page-questions-inline" />,
}))
vi.mock('@/components/activity/ActivityLog', () => ({
  ActivityLog: () => <div data-testid="page-activity" />,
}))
vi.mock('@/components/logs/LogsView', () => ({
  LogsView: () => <div data-testid="page-logs" />,
}))
vi.mock('@/components/quality/QualityHealthPanel', () => ({
  QualityHealthPanel: () => <div data-testid="page-quality" />,
}))
vi.mock('@/components/instructions/InstructionsPage', () => ({
  InstructionsPage: () => <div data-testid="page-instructions" />,
}))
vi.mock('@/components/runners/RunnersPage', () => ({
  RunnersPage: () => <div data-testid="page-runners" />,
}))
vi.mock('@/components/charters/ChartersPage', () => ({
  ChartersPage: () => <div data-testid="page-charters" />,
}))
vi.mock('@/components/environment/WorktreesPanel', () => ({
  WorktreesPanel: () => <div data-testid="page-worktrees" />,
}))
vi.mock('@/components/environment/DiagnosticsPanel', () => ({
  DiagnosticsPanel: () => <div data-testid="page-diagnostics" />,
}))
vi.mock('@/components/accounting/AccountingPanel', () => ({
  AccountingPanel: () => <div data-testid="page-budgets" />,
}))
vi.mock('@/components/environment/ProjectSettingsPanel', () => ({
  ProjectSettingsPanel: () => <div data-testid="page-settings" />,
}))
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: () => <div data-testid="page-conversation" />,
}))
vi.mock('@/components/spec/SpecPage', () => ({
  SpecPage: () => <div data-testid="page-spec" />,
}))

// Stub the layout chrome too so the test focuses on routing.
vi.mock('@/components/layout/StatusBar', () => ({
  StatusBar: () => <div data-testid="status-bar" />,
}))
vi.mock('@/components/layout/SetupModal', () => ({
  SetupModal: () => null,
}))

import App from '@/App'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

describe('phase 5 App.tsx: rail-only navigation, tabs own project content', () => {
  beforeEach(() => {
    cleanup()
    window.history.pushState(null, '', '/')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
      mode: 'light',
    })
  })

  it('renders the default tab (overview) on initial mount', () => {
    render(withQueryClient(<App />))
    expect(screen.getByTestId('page-overview')).toBeInTheDocument()
  })

  it('does not mount any project page not selected', () => {
    render(withQueryClient(<App />))
    for (const id of ['page-tasks', 'page-spec', 'page-jobs', 'page-activity']) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })

  it('the rail carries no top-level destinations for project pages', () => {
    render(withQueryClient(<App />))
    for (const id of [
      'nav-tasks', 'nav-spec', 'nav-jobs', 'nav-activity', 'nav-environment',
      'nav-questions', 'nav-logs', 'nav-quality', 'nav-instructions',
      'nav-runners', 'nav-charters',
    ]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })

  it('switches tabs via the project tab bar', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('project-tab-tasks'))
    expect(screen.queryByTestId('page-overview')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-tasks')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('project-tab-jobs'))
    expect(screen.queryByTestId('page-tasks')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-jobs')).toBeInTheDocument()
  })

  it('reflects the active tab in the URL', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('project-tab-tasks'))
    expect(window.location.search).toContain('tab=tasks')
  })

  it('switches projects from the persistent header and drops scoped destination state', () => {
    window.history.pushState(
      null,
      '',
      '?project=proj-test&agent=claude&conversation=conv-1&document=spec%2Fspec.html',
    )
    render(withQueryClient(<App />))

    fireEvent.change(screen.getByRole('combobox', { name: 'Switch project' }), {
      target: { value: 'proj-other' },
    })

    expect(window.location.search).toContain('project=proj-other')
    expect(window.location.search).toContain('tab=overview')
    expect(window.location.search).not.toContain('agent=')
    expect(window.location.search).not.toContain('conversation=')
    expect(window.location.search).not.toContain('document=')
    expect(useConfigStore.getState().selectedProjectId).toBe('proj-other')
    expect(screen.getByRole('combobox', { name: 'Switch project' })).toHaveValue('proj-other')
  })

  it('offers the Spec tab as a place to focus on the specification', () => {
    // Both routes exist and mean different things: the tab is the specification as the thing you
    // are working on, the composer's Spec pill is it as the thing you are working beside.
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('project-tab-spec'))

    expect(window.location.search).toContain('tab=spec')
    expect(screen.getByTestId('page-spec')).toBeInTheDocument()
    // No conversation on this screen — that is the whole point of it.
    expect(screen.queryByTestId('page-conversation')).not.toBeInTheDocument()
  })

  it('Overview surfaces Questions inline without changing tab', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByText('Answer'))
    expect(screen.getByTestId('page-questions-inline')).toBeInTheDocument()
    expect(window.location.search).toContain('tab=overview')
  })

  it('Tasks contains Dependencies as an internal sub-view, the seven-column board still the default (task 8.11)', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('project-tab-tasks'))
    expect(screen.getByTestId('page-tasks')).toBeInTheDocument()
    expect(screen.queryByTestId('page-tasks-dependencies')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('tasks-view-dependencies'))
    expect(screen.queryByTestId('page-tasks')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-tasks-dependencies')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('tasks-view-board'))
    expect(screen.getByTestId('page-tasks')).toBeInTheDocument()
    expect(screen.queryByTestId('page-tasks-dependencies')).not.toBeInTheDocument()
  })

  it('Activity contains Logs as an internal sub-view', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('project-tab-activity'))
    expect(screen.getByTestId('page-activity')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('activity-subview-logs'))
    expect(screen.queryByTestId('page-activity')).not.toBeInTheDocument()
    expect(screen.getByTestId('page-logs')).toBeInTheDocument()
  })

  it('Environment contains Quality, Instructions, Runners, Charters, Worktrees, Diagnostics, Budgets, and Settings', () => {
    render(withQueryClient(<App />))
    fireEvent.click(screen.getAllByRole('button', { name: /^Configure /i })[0])
    const sections: Array<[string, string]> = [
      ['environment-section-quality', 'page-quality'],
      ['environment-section-instructions', 'page-instructions'],
      ['environment-section-runners', 'page-runners'],
      ['environment-section-charters', 'page-charters'],
      ['environment-section-worktrees', 'page-worktrees'],
      ['environment-section-diagnostics', 'page-diagnostics'],
      ['environment-section-budgets', 'page-budgets'],
      ['environment-section-settings', 'page-settings'],
    ]
    for (const [sectionTestId, pageTestId] of sections) {
      fireEvent.click(screen.getByTestId(sectionTestId))
      expect(screen.getByTestId(pageTestId)).toBeInTheDocument()
    }
  })

  it('mounts a direct agent conversation URL straight into the conversation view', () => {
    window.history.pushState(null, '', '?project=proj-test&agent=claude&conversation=conv-1')
    render(withQueryClient(<App />))
    expect(screen.getByTestId('page-conversation')).toBeInTheDocument()
    expect(screen.queryByTestId('page-overview')).not.toBeInTheDocument()
  })

  /* The document is what the operator is working on, not a property of the thread they are
   * working on it in (operator: "a memory between agents"). */
  it('keeps an open document open when the agent changes', () => {
    window.history.pushState(
      null, '',
      '?project=proj-test&agent=claude&conversation=conv-1&document=spec%2Fspec.html',
    )
    render(withQueryClient(<App />))

    fireEvent.click(screen.getByTestId('rail-agent-proj-test-codex'))

    expect(window.location.search).toContain('agent=codex')
    expect(window.location.search).toContain('document=spec%2Fspec.html')
  })

  it('keeps it closed when it was closed', () => {
    window.history.pushState(null, '', '?project=proj-test&agent=claude&conversation=conv-1')
    render(withQueryClient(<App />))

    fireEvent.click(screen.getByTestId('rail-agent-proj-test-codex'))

    expect(window.location.search).toContain('agent=codex')
    expect(window.location.search).not.toContain('document')
  })

  it('does not resurrect a document when arriving from a project tab', () => {
    // The memory is of what is on screen, not a preference that outlives leaving the surface.
    window.history.pushState(
      null, '',
      '?project=proj-test&agent=claude&conversation=conv-1&document=spec%2Fspec.html',
    )
    render(withQueryClient(<App />))
    // The project tab bar only exists on a project destination, so leave the conversation first.
    fireEvent.click(screen.getByTestId('project-name-proj-test'))
    fireEvent.click(screen.getByTestId('rail-agent-proj-test-claude'))

    expect(window.location.search).toContain('agent=claude')
    expect(window.location.search).not.toContain('document')
  })
})
