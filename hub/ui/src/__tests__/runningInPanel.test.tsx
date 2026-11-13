import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AgentSummary } from '@/api/agents'
import type { Job, LoopSummary } from '@/api/jobs'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import { useConfigStore } from '@/store/configStore'

/* The Running tab inside the conversation view (`the-side-panel-s-running-tab`, FR-1, FR-8): a panel
 * stored with a Loops tab shows Running in its place and offers no Loops anywhere; selecting a
 * build, loop and job row opens the document at its builds, the loop's tab and the Jobs page; Answer
 * goes to the questions. Fixtures are in the order each route returns them. */

let builds: ProjectBuildRow[] = []
let loops: LoopSummary[] = []
let jobs: Job[] = []

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

vi.mock('@/api/projectBuilds', () => ({ useProjectBuilds: () => ({ data: builds, isLoading: false }) }))
vi.mock('@/api/loops', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/loops')>()),
  useLoops: () => ({ data: loops, isLoading: false }),
}))
vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/jobs')>()),
  useJobs: () => ({ data: jobs, isLoading: false }),
  useArchivedJobs: () => ({ data: [] }),
}))

vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecDocuments: () => ({ data: { documents: [] } }),
  useSpecList: () => ({
    data: { specs: [], home: null, diagnostics: [], missing: [] },
    isLoading: false,
    refetch: () => {},
  }),
  useSpecEvents: () => {},
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgentOutput: () => ({ lines: [], isLoading: false }),
  useAgents: () => ({ data: [] }),
  useAgentLaunchability: () => ({ data: { agents: {} } }),
  useAgentTimeline: () => ({ data: { events: [], runs: {} } }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agentChat')>()),
  useAgentConversations: () => ({ data: [] }),
  useAgentChatHistory: () => ({ data: { conversation_id: null, session_id: null, agent: 'dev', entries: [], runs: {} }, isLoading: false }),
  useAgentRecentChat: () => ({ data: { conversation_id: null, session_id: null, agent: 'dev', entries: [], runs: {} }, isLoading: false }),
}))
vi.mock('@/api/questions', () => ({
  useQuestions: () => ({ data: [] }),
  useAnswerQuestion: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeclineQuestion: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/permissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/permissions')>()),
  usePendingPermissionRequests: () => ({ data: [] }),
  useDecidePermissionRequest: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/api/checkpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/checkpoints')>()),
  useCheckpoints: () => ({ data: [] }),
  useProjectCheckpoints: () => ({ data: undefined }),
}))
vi.mock('@/api/queue', () => ({
  useQueuedEntries: () => ({ data: [] }),
  useQueueStatus: () => ({ data: { waiting_count: 0 } }),
  withdrawQueueEntry: vi.fn(),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: undefined }),
}))
// The document and the loop's own tab are other capabilities: stubs record what Running asked for.
vi.mock('@/components/spec/page/SpecPanelContainer', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/spec/page/SpecPanelContainer')>()),
  SpecPanelContainer: (props: { path: string; initialAnchor?: string | null }) => (
    <div data-testid="spec-stub" data-anchor={props.initialAnchor ?? ''}>
      {props.path}
    </div>
  ),
}))
vi.mock('@/components/spec/LoopTab', () => ({
  LoopTab: ({ loopId }: { loopId: string }) => <div data-testid="loop-stub">{loopId}</div>,
}))

import { ConversationView } from '@/components/agents/ConversationView'
import { migratePanelTabs, usePanelTabsStore } from '@/store/panelTabsStore'

const PROJECT_ID = 'proj-running-panel'
const NOW = Date.now()
const hoursAgo = (h: number) => new Date(NOW - h * 3600_000).toISOString()
const AGENT: AgentSummary = { name: 'dev', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }

function renderConversation(handlers: { onOpenJobs?: () => void; onOpenQuestions?: () => void } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConversationView
        agent={AGENT}
        conversationId={null}
        projectId={PROJECT_ID}
        document={null}
        onSelectConversation={() => {}}
        onOpenDocument={() => {}}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
        onOpenJobs={handlers.onOpenJobs}
        onOpenQuestions={handlers.onOpenQuestions}
      />
    </QueryClientProvider>,
  )
}

function seed(): void {
  builds = [
    {
      id: 'build-1',
      document_id: 'spdoc-1',
      document_title: 'Ship the thing',
      state: 'running',
      driver: 'flow',
      level: 'reviewed',
      lead: null,
      loop_id: 'loop-1',
      loop: { id: 'loop-1', name: 'Ship loop', enabled: true },
      tasks_total: 3,
      tasks_done: 1,
      tasks_landing: 0,
      landings: [],
      spent_usd: 1.5,
      stop_reason: null,
      created_at: hoursAgo(1),
      stopped_at: null,
      open_questions: 1,
      question: { id: 'q-1', question: 'Which?', from_agent: 'dev', conversation_id: 'conv-1', created_at: hoursAgo(0.5) },
    },
  ]
  loops = [
    { id: 'loop-1', label: 'Ship loop', purpose: '', stop_when_queue_empties: true, ending_state: null, queue: {}, open_questions: 0, firing_active: false },
    { id: 'loop-2', label: 'Nightly sweep', purpose: '', stop_when_queue_empties: false, ending_state: null, queue: {}, open_questions: 0, firing_active: false, stall_reason: 'No agent is free' },
  ] as LoopSummary[]
  jobs = [{ id: 'job-9', project_id: 'p', name: 'Weekly digest', agent: 'dev', message: 'm', cron: '0 9 * * 1', session_mode: 'new', enabled: true, source: 'hub', created_at: hoursAgo(100), run_count: 0 }] as Job[]
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  builds = []
  loops = []
  jobs = []
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: PROJECT_ID, isConfigured: true, bootstrapState: 'ready', mode: 'light' })
})

describe('a stored Loops tab is Running (FR-1)', () => {
  it('ac-restore: shows Running in the Loops strip position, visible, and offers Loops nowhere', () => {
    seed()
    usePanelTabsStore.setState({
      projects: migratePanelTabs(
        { [PROJECT_ID]: { tabs: [{ id: 'specs', revealRequestId: 0 }, { id: 'loops', revealRequestId: 0 }], activeTabId: 'loops', isOpen: true } },
        1,
      ),
    })
    renderConversation()
    const strip = screen.getByTestId('panel-tab-strip')
    expect(within(strip).getAllByRole('tab').map((t) => t.textContent)).toEqual(['Specs', 'Running'])
    expect(screen.getByTestId('panel-tab-running')).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('running-tab')).toBeInTheDocument()
    expect(screen.queryByText('Loops')).not.toBeInTheDocument()
    expect(screen.queryByTestId('panel-tab-loops')).not.toBeInTheDocument()
  })

  it('the empty-state launcher offers Running, counting what needs the operator or is working, and no Loops card', () => {
    seed()
    usePanelTabsStore.setState({ projects: {} })
    usePanelTabsStore.getState().setShellOpen(PROJECT_ID, true)
    renderConversation()
    expect(screen.getByTestId('panel-launch-running')).toBeInTheDocument()
    // The build asks a question and the nightly loop is stalled: two need the operator.
    expect(screen.getByTestId('panel-launch-badge-running')).toHaveTextContent('2')
    expect(screen.queryByTestId('panel-launch-loops')).not.toBeInTheDocument()
  })
})

describe('Running rows open their item and Answer goes to the question (FR-4, FR-8)', () => {
  function openRunning(handlers: Parameters<typeof renderConversation>[0] = {}) {
    seed()
    usePanelTabsStore.setState({ projects: {} })
    usePanelTabsStore.getState().openTab(PROJECT_ID, 'running')
    return renderConversation(handlers)
  }

  it('ac-open: a build opens its document at its builds', () => {
    openRunning()
    fireEvent.click(screen.getByTitle('Open Ship the thing'))
    const stub = screen.getByTestId('spec-stub')
    expect(stub).toHaveAttribute('data-anchor', 'section-builds')
    expect(usePanelTabsStore.getState().projects[PROJECT_ID].activeTabId).toBe('spec:spdoc-1')
  })

  it('ac-open: a loop opens its detail tab', () => {
    openRunning()
    fireEvent.click(screen.getByTitle('Open Nightly sweep'))
    expect(screen.getByTestId('loop-stub')).toHaveTextContent('loop-2')
  })

  it('ac-open: a job opens the Jobs page', () => {
    const onOpenJobs = vi.fn()
    openRunning({ onOpenJobs })
    fireEvent.click(screen.getByTitle('Open Weekly digest'))
    expect(onOpenJobs).toHaveBeenCalledTimes(1)
  })

  it('ac-question: Answer takes the operator to where the question is answered', () => {
    const onOpenQuestions = vi.fn()
    openRunning({ onOpenQuestions })
    const group = screen.getByRole('region', { name: 'Needs you' })
    fireEvent.click(within(group).getAllByRole('button', { name: 'Answer' })[0])
    expect(onOpenQuestions).toHaveBeenCalledTimes(1)
  })

  it('ac-stall: Look opens the loop record', () => {
    openRunning()
    const group = screen.getByRole('region', { name: 'Needs you' })
    expect(within(group).getByText('No agent is free')).toBeInTheDocument()
    fireEvent.click(within(group).getByRole('button', { name: 'Look' }))
    expect(screen.getByTestId('loop-stub')).toHaveTextContent('loop-2')
  })
})
