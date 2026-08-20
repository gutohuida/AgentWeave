/**
 * The rail's add-agent button must scope the creation dialog to the project it belongs to.
 *
 * This is a regression test for a defect the operator hit in the real app on 2026-08-19: they
 * clicked add-agent on one project and the agent was created in another. The cause was that
 * `onAddAgent` was the only rail action that opened a project-scoped surface *without navigating*.
 * Selection in `App.tsx` is derived from the destination, and every hook the dialog reads
 * (`useCreateAgent`, `useCharters`, `useProviderLaunchability`) resolves the selected project — so
 * the dialog silently belonged to whichever project was already selected.
 *
 * Why this is asserted at the App level rather than on the dialog: the existing dialog tests in
 * `agentCreationUi.test.tsx` mock `useCreateAgent` wholesale, so they cannot see which project the
 * request would address, and passed throughout the life of the bug. The wiring is the thing that
 * was wrong, so the wiring is what is tested.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

vi.stubGlobal(
  'fetch',
  vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
)

const project = (id: string, name: string) => ({
  id,
  name,
  working_directory: `C:/work/${name}`,
  path_display: `C:/work/${name}`,
  directory_state: 'available',
  last_opened_at: null,
  last_seen_at: null,
  hop_budget: 20,
  turn_delivery_cap: 20,
  agent_budget: 10,
  token_budget: null,
  allow_agent_jobs: true,
  agents: [],
})

const PROJECTS = [project('proj-a', 'Alpha'), project('proj-b', 'Beta')]

vi.mock('@/api/projects', () => ({
  useProjects: () => ({ data: PROJECTS, isLoading: false }),
  // Must list BOTH ids: `bootstrap()` clears a selection it cannot find, which would reset the
  // very state this test is about.
  fetchProjectSummaries: vi.fn(async () => [{ id: 'proj-a' }, { id: 'proj-b' }]),
  useOpenProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useCreateProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useUpdateProjectSettings: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRelocateProject: () => ({ mutate: vi.fn(), error: null, isPending: false }),
}))
// Partial: the dialog reaches for `useCreateAgent` from this module too, and a whole-module mock
// that lists only what App happens to use breaks the moment a child imports a sibling export.
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecList: () => ({
    data: { specs: [], home: null, diagnostics: [], missing: [] },
    isLoading: false,
    refetch: () => {},
  }),
  useSpec: () => ({ data: undefined, refetch: () => {} }),
  useSpecEvents: () => {},
}))

vi.mock('@/components/overview/OverviewPage', () => ({ OverviewPage: () => <div data-testid="page-overview" /> }))
vi.mock('@/components/tasks/TasksBoard', () => ({ TasksBoard: () => <div /> }))
vi.mock('@/components/jobs/JobsPage', () => ({ JobsPage: () => <div /> }))
vi.mock('@/components/questions/QuestionsPanel', () => ({ QuestionsPanel: () => <div /> }))
vi.mock('@/components/activity/ActivityLog', () => ({ ActivityLog: () => <div /> }))
vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div /> }))
vi.mock('@/components/quality/QualityHealthPanel', () => ({ QualityHealthPanel: () => <div /> }))
vi.mock('@/components/instructions/InstructionsPage', () => ({ InstructionsPage: () => <div /> }))
vi.mock('@/components/runners/RunnersPage', () => ({ RunnersPage: () => <div /> }))
vi.mock('@/components/charters/ChartersPage', () => ({ ChartersPage: () => <div /> }))
vi.mock('@/components/environment/WorktreesPanel', () => ({ WorktreesPanel: () => <div /> }))
vi.mock('@/components/environment/DiagnosticsPanel', () => ({ DiagnosticsPanel: () => <div /> }))
vi.mock('@/components/accounting/AccountingPanel', () => ({ AccountingPanel: () => <div /> }))
vi.mock('@/components/environment/ProjectSettingsPanel', () => ({ ProjectSettingsPanel: () => <div /> }))
vi.mock('@/components/agents/AgentOutputPanel', () => ({ AgentOutputPanel: () => <div /> }))
vi.mock('@/components/spec/SpecPage', () => ({ SpecPage: () => <div /> }))
vi.mock('@/components/layout/StatusBar', () => ({ StatusBar: () => <div /> }))
vi.mock('@/components/layout/SetupModal', () => ({ SetupModal: () => null }))

import App from '@/App'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

describe('the rail scopes agent creation to the project it was clicked on', () => {
  beforeEach(() => {
    cleanup()
    window.history.pushState(null, '', '/')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
      mode: 'light',
    })
  })

  it('selects the clicked project, so the dialog addresses it and not the selected one', () => {
    render(withQueryClient(<App />))
    expect(useConfigStore.getState().selectedProjectId).toBe('proj-a')

    fireEvent.click(screen.getByTestId('rail-add-agent-proj-b'))

    // The assertion that matters: the dialog's hooks all resolve `selectedProjectId`, so this is
    // the project the POST will address. Before the fix this stayed 'proj-a' and the agent was
    // created in Alpha while the operator was looking at Beta.
    expect(useConfigStore.getState().selectedProjectId).toBe('proj-b')
  })

  it('opens the creation dialog when the rail asks for it', () => {
    render(withQueryClient(<App />))
    expect(screen.queryByLabelText('Agent name')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('rail-add-agent-proj-b'))
    expect(screen.getByLabelText('Agent name')).toBeInTheDocument()
  })

  it('scopes to the already-selected project too, when that is the one clicked', () => {
    // The fix must not overcorrect into "always switch away".
    render(withQueryClient(<App />))
    fireEvent.click(screen.getByTestId('rail-add-agent-proj-a'))
    expect(useConfigStore.getState().selectedProjectId).toBe('proj-a')
  })
})
