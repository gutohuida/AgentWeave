import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useConfigStore } from '@/store/configStore'

vi.mock('@/hooks/useSSE', () => ({
  // The rail's live dot reads this; a whole-module mock has to carry it or Sidebar throws.
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

vi.mock('@/api/agents', () => ({
  useAgents: () => ({
    data: [{
      name: 'claude', status: 'idle', message_count: 0, active_task_count: 0, color_index: 2,
    }],
    isLoading: false,
  }),
}))
vi.mock('@/api/projects', () => ({
  useProjects: () => ({
    data: [{
      id: 'proj-test', name: 'AgentWeave', working_directory: 'C:/work/AgentWeave',
      path_display: 'C:/work/AgentWeave', directory_state: 'available', last_opened_at: null,
      last_seen_at: null, hop_budget: 20, turn_delivery_cap: 20, agent_budget: 10,
      token_budget: null, allow_agent_jobs: true,
      agents: [{ id: 'agent-claude', name: 'claude', color_index: 2, status: 'idle', last_seen: null }],
    }],
    isLoading: false,
  }),
  fetchProjectSummaries: vi.fn(async () => [{ id: 'proj-test' }]),
  useOpenProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useCreateProject: () => ({ mutate: vi.fn(), reset: vi.fn(), error: null, isPending: false }),
  useUpdateProjectSettings: () => ({ mutate: vi.fn(), error: null, isPending: false }),
  useRelocateProject: () => ({ mutate: vi.fn(), error: null, isPending: false }),
}))
vi.mock('@/api/status', () => ({
  useStatus: () => ({ data: { project_id: 'proj-test', project_name: 'AgentWeave' } }),
  useSessionSync: () => ({ data: undefined }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/messages', () => ({ useMessages: () => ({ data: [] }) }))

vi.mock('@/components/overview/OverviewPage', () => ({
  OverviewPage: ({ onNavigate }: { onNavigate: (destination: string) => void }) => (
    <div data-testid="project-overview">
      <button onClick={() => onNavigate('agent:claude')}>Open claude from overview</button>
    </div>
  ),
}))
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: ({ agent, onBackToProject }: {
    agent: { name: string }
    onBackToProject: () => void
  }) => (
    <div data-testid="agent-conversation">
      <header data-testid="conversation-header">
        <button onClick={onBackToProject}>Back to project</button>
        <span>{agent.name}</span>
      </header>
    </div>
  ),
}))

vi.mock('@/components/tasks/TasksBoard', () => ({ TasksBoard: () => <div /> }))
vi.mock('@/components/questions/QuestionsPanel', () => ({ QuestionsPanel: () => <div /> }))
vi.mock('@/components/activity/ActivityLog', () => ({ ActivityLog: () => <div /> }))
vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div /> }))
vi.mock('@/components/jobs/JobsPage', () => ({ JobsPage: () => <div /> }))
vi.mock('@/components/instructions/InstructionsPage', () => ({ InstructionsPage: () => <div /> }))
vi.mock('@/components/quality/QualityHealthPanel', () => ({ QualityHealthPanel: () => <div /> }))
vi.mock('@/components/spec/SpecPage', () => ({ SpecPage: () => <div /> }))
vi.mock('@/components/layout/StatusBar', () => ({ StatusBar: () => <div /> }))
vi.mock('@/components/layout/SetupModal', () => ({ SetupModal: () => null }))

import App from '@/App'

function withClient(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      {node}
    </QueryClientProvider>
  )
}

describe('phase 1 conversation-first shell', () => {
  beforeEach(() => {
    cleanup()
    window.history.pushState(null, '', '/')
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      selectedProjectId: 'proj-test',
      isConfigured: true,
      bootstrapState: 'ready',
      mode: 'light',
    })
  })

  it('keeps project-name navigation separate from expansion', () => {
    render(withClient(<App />))
    expect(screen.getByTestId('project-overview')).toBeInTheDocument()
    expect(screen.getByTestId('rail-agent-color-proj-test-claude')).toHaveStyle({
      background: 'var(--agent-3)',
    })
    fireEvent.click(screen.getByTestId('project-expander-proj-test'))
    expect(screen.queryByTestId('rail-agent-proj-test-claude')).not.toBeInTheDocument()
    expect(screen.getByTestId('project-overview')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('project-name-proj-test'))
    expect(screen.getByTestId('project-overview')).toBeInTheDocument()
  })

  it.each(['rail', 'overview'])('opens claude directly from the %s', (source) => {
    render(withClient(<App />))
    fireEvent.click(source === 'rail'
      ? screen.getByTestId('rail-agent-proj-test-claude')
      : screen.getByText('Open claude from overview'))
    expect(screen.getByTestId('agent-conversation')).toBeInTheDocument()
    expect(screen.queryByTestId('project-overview')).not.toBeInTheDocument()
    expect(screen.queryByText('Select an agent to view details.')).not.toBeInTheDocument()
    expect(screen.getAllByTestId('conversation-header')).toHaveLength(1)
  })

  it('returns to the containing project in one action', () => {
    render(withClient(<App />))
    fireEvent.click(screen.getByTestId('rail-agent-proj-test-claude'))
    fireEvent.click(screen.getByText('Back to project'))
    expect(screen.getByTestId('project-overview')).toBeInTheDocument()
  })

  it('does not offer Agents or Messages destinations', () => {
    render(withClient(<App />))
    expect(screen.queryByTestId('nav-agents')).not.toBeInTheDocument()
    expect(screen.queryByTestId('nav-messages')).not.toBeInTheDocument()
  })
})
