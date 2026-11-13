import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AgentSummary } from '@/api/agents'
import type { ConversationChanges } from '@/api/changes'
import { useConfigStore } from '@/store/configStore'

/* The Changes tab in the conversation's panel (`the-side-panel-s-changes-tab-shows-what-the-agent-changed`):
 * offered beside Files wherever the app is opened (FR-10), and the states it shows (FR-5, FR-9, FR-6, FR-7). */

let changes: ConversationChanges | undefined

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/jobs')>()),
  useJobs: () => ({ data: [], isLoading: false }),
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
vi.mock('@/api/workspace', () => ({
  useWorkspacePaths: () => ({ data: [] }),
  useWorkspaceFile: () => ({ data: undefined, isLoading: true, error: null }),
}))
vi.mock('@/api/runners', () => ({ useRunners: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/modelCatalog')>()),
  useModelCatalog: () => ({ data: undefined }),
}))
// The document and the loop's own tab are other capabilities: stubs record what Running asked for.
vi.mock('@/api/projectBuilds', () => ({ useProjectBuilds: () => ({ data: [], isLoading: false }) }))
vi.mock('@/api/loops', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/loops')>()),
  useLoops: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/api/changes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/changes')>()),
  useConversationChanges: () => ({ data: changes, isError: false }),
  useChangePatch: (_c: string | null, path: string | null) => ({
    data: path
      ? { path, patch: path === 'big.py' ? '@@ -1 +1 @@\n-a\n+b' : path === 'blob.bin' ? '' : '@@ -1 +1 @@\n-old\n+new line', binary: path === 'blob.bin', truncated: path === 'big.py', total_lines: 6000 }
      : undefined,
    isError: false,
  }),
}))

import { ConversationView } from '@/components/agents/ConversationView'
import { usePanelTabsStore } from '@/store/panelTabsStore'

const PROJECT_ID = 'proj-changes-tab'
const AGENT: AgentSummary = { name: 'dev', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }
const file = (path: string, extra: object = {}) => ({ path, status: 'M', added: 1, removed: 1, binary: false, ...extra })
const base: ConversationChanges = { state: 'ok', agent: 'dev', branch: 'agentweave/dev', base: 'main', turn: [], since_base: [], running: false, working_now: [] }

function renderConversation() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConversationView agent={AGENT} conversationId="conv-1" projectId={PROJECT_ID} document={null} onSelectConversation={() => {}} onOpenDocument={() => {}} onBackToProject={() => {}} onOpenAgentSettings={() => {}} />
    </QueryClientProvider>,
  )
}

function openChanges() {
  usePanelTabsStore.setState({ projects: { [PROJECT_ID]: { tabs: [{ id: 'changes', revealRequestId: 0 }], activeTabId: 'changes', isOpen: true } } })
  renderConversation()
}

beforeEach(() => {
  cleanup()
  localStorage.clear()
  changes = undefined
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://203.0.113.7:8000', selectedProjectId: PROJECT_ID, isConfigured: true, bootstrapState: 'ready', mode: 'light' })
})

describe('Changes is offered where Files is (FR-10)', () => {
  it('ac-remote: from a non-local address, the launcher offers Changes beside Files', () => {
    usePanelTabsStore.setState({ projects: { [PROJECT_ID]: { tabs: [], activeTabId: null, isOpen: true } } })
    renderConversation()
    expect(screen.getByTestId('panel-launch-files')).toBeInTheDocument()
    expect(screen.getByTestId('panel-launch-changes')).toBeInTheDocument()
  })
})

describe('the Changes tab', () => {
  it('ac-diff: selecting a file shows its diff and the conversation stays', () => {
    changes = { ...base, turn: [file('src/a.py')], since_base: [file('src/a.py')] }
    openChanges()
    fireEvent.click(screen.getByText('a.py'))
    expect(screen.getByTestId('changes-diff')).toHaveTextContent('new line')
    expect(screen.getByTestId('conversation-pane')).toBeVisible()
  })

  it('ac-working-now: names uncommitted files while a turn runs', () => {
    changes = { ...base, running: true, working_now: ['src/wip.py'] }
    openChanges()
    expect(screen.getByTestId('changes-working-now')).toHaveTextContent('src/wip.py')
  })

  it('ac-empty: says nothing changed, and that there is no checkout, with no error code', () => {
    changes = { ...base, state: 'empty' }
    openChanges()
    expect(screen.getByTestId('changes-tab')).toHaveTextContent('dev has changed nothing yet')
    cleanup()
    changes = { state: 'no_checkout', agent: 'dev', message: 'dev has no checkout of its own: it is read-only.', turn: [], since_base: [], running: false, working_now: [] }
    openChanges()
    expect(screen.getByTestId('changes-tab')).toHaveTextContent('no checkout')
    expect(screen.getByTestId('changes-tab').textContent).not.toMatch(/\b(4|5)\d\d\b/)
  })

  it('ac-large: a binary file has no body and a long diff says it is truncated', () => {
    changes = { ...base, turn: [file('blob.bin', { binary: true }), file('big.py')] }
    openChanges()
    fireEvent.click(screen.getByText('blob.bin'))
    expect(screen.getByTestId('changes-binary')).toBeInTheDocument()
    expect(screen.queryByTestId('changes-diff')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('big.py'))
    expect(screen.getByTestId('changes-truncated')).toHaveTextContent('6,000')
    expect(screen.getByTestId('changes-diff')).toBeInTheDocument()
  })

  it('ac-open-file: opening a listed file opens a Files tab on it', () => {
    changes = { ...base, turn: [file('src/a.py')] }
    openChanges()
    fireEvent.click(screen.getByRole('button', { name: 'Open src/a.py in Files' }))
    const tabs = usePanelTabsStore.getState().projects[PROJECT_ID]!
    expect(tabs.activeTabId).toBe('file:src/a.py')
  })
})
