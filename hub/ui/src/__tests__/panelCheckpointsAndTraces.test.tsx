import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { AgentSummary } from '@/api/agents'
import type { CheckpointNote, ProjectCheckpoint } from '@/api/checkpoints'
import type { TraceTarget } from '@/store/panelTabsStore'
import { useConfigStore } from '@/store/configStore'

/* leaner-navigation D4: Checkpoints and Trace are side-panel tabs opened on demand. The thread's
 * ⋯ menu opens them (FR-4, FR-8), a link to one checkpoint opens its thread's tab on it (FR-10),
 * and none of it moves the address off the conversation. Fixtures are in the order the
 * checkpoints route returns them: newest first. */

const AGENT: AgentSummary = { name: 'dev', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }
const PROJECT_ID = 'proj-panel-on-demand'

function checkpoint(over: Partial<ProjectCheckpoint> & { id: string }): ProjectCheckpoint {
  return {
    conversation_id: 'conv-1',
    agent: 'dev',
    trigger: 'operator',
    status: 'ready',
    lineage_id: over.id,
    title: `Title of ${over.id}`,
    summary: `Summary of ${over.id}`,
    body: '## Objective\n\nShip the tab.\n',
    created_at: '2026-11-22T12:00:00Z',
    covered_runs: [],
    ...over,
  }
}

// Every section the Checkpoints page showed: findings, runs covered, files, open questions, cited, notes.
const FULL = checkpoint({
  id: 'ckpt-full',
  status: 'failed',
  probe_findings: [{ dimension: 'files', missing: ['src/a.ts'], invented: [] }],
  covered_runs: [{ run_id: 'run-7', agent: 'dev', status: 'completed', started_at: '2026-11-22T11:00:00Z', ended_at: '2026-11-22T11:05:00Z' }],
  files_changed: ['src/a.ts'],
  open_questions: [{ id: 'q-1', question: 'Which tab first?' }],
  citations: [{ id: 'obs-1', preview: 'The row scrolled at 960 px' }],
})
const OLDER = checkpoint({ id: 'ckpt-older', created_at: '2026-11-21T12:00:00Z' })
const NOTE: CheckpointNote = {
  id: 'note-1',
  agent: 'dev',
  run_id: 'run-7',
  intent: 'Finish the panel tab',
  suspicions: [],
  warnings: [],
  consumed_by_checkpoint_id: 'ckpt-full',
  created_at: '2026-11-22T11:06:00Z',
}

let listed: ProjectCheckpoint[] = [FULL, OLDER]
const listCalls: Array<Record<string, unknown>> = []

vi.mock('@/hooks/useSSE', () => ({
  useSSE: () => {},
  useSSEConnectionState: () => 'open',
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))
vi.mock('@/api/checkpoints', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/checkpoints')>()),
  useCheckpoints: () => ({ data: [] }),
  useProjectCheckpoints: (filters: Record<string, unknown> = {}) => {
    listCalls.push(filters)
    const rows = listed.filter(
      (row) => (!filters.conversationId || row.conversation_id === filters.conversationId) && (!filters.agent || row.agent === filters.agent),
    )
    return { data: { checkpoints: rows, lineage: null }, isLoading: false, error: null, refetch: () => {} }
  },
  useCheckpointNotes: () => ({ data: { notes: [NOTE] }, error: null, refetch: () => {} }),
}))
vi.mock('@/api/agentChat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agentChat')>()),
  useAgentConversations: () => ({ data: [{ id: 'conv-1', agent: 'dev', title: 'Wire the tabs' }] }),
  useProjectConversations: () => ({ data: { conversations: [{ id: 'conv-1', agent: 'dev', title: 'Wire the tabs', lifecycle: 'open' }] }, error: null, refetch: () => {} }),
}))
vi.mock('@/api/agents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agents')>()),
  useAgents: () => ({ data: [AGENT], error: null, refetch: () => {} }),
}))
vi.mock('@/api/spec', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/spec')>()),
  useSpecDocuments: () => ({ data: { documents: [] } }),
  useSpecList: () => ({ data: { specs: [], home: null, diagnostics: [], missing: [] }, isLoading: false, refetch: () => {} }),
  useSpecEvents: () => {},
}))
vi.mock('@/api/projectBuilds', () => ({ useProjectBuilds: () => ({ data: [], isLoading: false }) }))
vi.mock('@/api/loops', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/loops')>()),
  useLoops: () => ({ data: [], isLoading: false }),
}))
vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/jobs')>()),
  useJobs: () => ({ data: [], isLoading: false }),
  useArchivedJobs: () => ({ data: [] }),
}))
// The thread itself is AgentOutputPanel's, tested in conversationControls: here its ⋯ items are
// buttons that call what the menu calls.
vi.mock('@/components/agents/AgentOutputPanel', () => ({
  AgentOutputPanel: (props: {
    onOpenCheckpointsPanel?: (checkpointId: string | null) => void
    onOpenTracePanel?: (target: TraceTarget) => void
  }) => (
    <div data-testid="thread">
      <button type="button" onClick={() => props.onOpenCheckpointsPanel?.(null)}>Checkpoints (2)</button>
      <button type="button" onClick={() => props.onOpenTracePanel?.({ scope: 'thread' })}>Trace of this thread</button>
      <button type="button" onClick={() => props.onOpenTracePanel?.({ scope: 'run', runId: 'run-7' })}>Trace of the latest run</button>
    </div>
  ),
}))
// The trace bodies are the drawers' own, tested with them; here only which trace the tab shows.
vi.mock('@/components/traces/ConversationTraceDrawer', () => ({
  ConversationTraceBody: ({ conversationId }: { conversationId: string }) => <div data-testid="thread-trace-body">{conversationId}</div>,
}))
vi.mock('@/components/traces/TraceDrawer', () => ({
  TraceDrawerBody: ({ runId }: { runId?: string }) => <div data-testid="run-trace-body">{runId}</div>,
  TraceButton: ({ runId, testId }: { runId?: string; testId?: string }) => <button type="button" data-testid={testId}>{runId}</button>,
}))

import { ConversationView } from '@/components/agents/ConversationView'
import { usePanelTabsStore } from '@/store/panelTabsStore'

const ADDRESS = `/?project=${PROJECT_ID}&agent=dev&conversation=conv-1`

function renderThread(over: { checkpoint?: string | null; onCheckpointConsumed?: () => void } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ConversationView
        agent={AGENT}
        conversationId="conv-1"
        projectId={PROJECT_ID}
        document={null}
        onSelectConversation={() => {}}
        onOpenDocument={() => {}}
        onBackToProject={() => {}}
        onOpenAgentSettings={() => {}}
        {...over}
      />
    </QueryClientProvider>,
  )
}

const rowIds = () => within(screen.getByTestId('panel-tab-strip')).queryAllByTestId(/^panel-tab-(?!close|add)/).map((el) => el.dataset.testid)

beforeEach(() => {
  listed = [FULL, OLDER]
  listCalls.length = 0
  usePanelTabsStore.setState({ projects: {}, targets: {} })
  useConfigStore.setState({ selectedProjectId: PROJECT_ID })
  window.history.replaceState(null, '', ADDRESS)
})

describe('thread-trace-panel (FR-4)', () => {
  it('opens a Trace tab on the thread, then on the latest run, in the thread; closing it removes it', () => {
    renderThread()
    expect(screen.queryByTestId('panel-tab-trace')).toBeNull()

    fireEvent.click(screen.getByText('Trace of this thread'))
    expect(rowIds()).toEqual(['panel-tab-trace'])
    expect(screen.getByTestId('trace-tab')).toHaveAttribute('data-scope', 'thread')
    expect(screen.getByTestId('thread-trace-body')).toHaveTextContent('conv-1')

    fireEvent.click(screen.getByText('Trace of the latest run'))
    // Single-instance: the same tab, now on the run.
    expect(rowIds()).toEqual(['panel-tab-trace'])
    expect(screen.getByTestId('trace-tab')).toHaveAttribute('data-scope', 'run')
    expect(screen.getByTestId('run-trace-body')).toHaveTextContent('run-7')
    expect(window.location.search).toBe(ADDRESS.slice(1))

    fireEvent.click(screen.getByTestId('panel-tab-close-trace'))
    expect(screen.queryByTestId('panel-tab-trace')).toBeNull()
    expect(usePanelTabsStore.getState().targets[PROJECT_ID]?.trace).toBeUndefined()
  })

  it('is not one of the tabs the panel offers to open', () => {
    renderThread()
    fireEvent.click(screen.getByText('Trace of this thread'))
    fireEvent.click(screen.getByTestId('panel-tab-close-trace'))
    act(() => usePanelTabsStore.getState().setShellOpen(PROJECT_ID, true))
    expect(screen.getByTestId('panel-empty-state')).toBeInTheDocument()
    expect(screen.queryByTestId('panel-launch-trace')).toBeNull()
    expect(screen.queryByTestId('panel-launch-checkpoints')).toBeNull()
  })
})

describe('thread-checkpoints-panel (FR-8)', () => {
  it('lists the thread’s checkpoints, opens one with every section, stays in the thread, and closes', () => {
    renderThread()
    expect(screen.queryByTestId('panel-tab-checkpoints')).toBeNull()

    fireEvent.click(screen.getByText('Checkpoints (2)'))
    expect(rowIds()).toEqual(['panel-tab-checkpoints'])
    expect(listCalls).toContainEqual({ conversationId: 'conv-1' })
    const list = screen.getByTestId('checkpoints-list')
    expect(within(list).getByText('Title of ckpt-full')).toBeInTheDocument()
    expect(within(list).getByText('Title of ckpt-older')).toBeInTheDocument()

    fireEvent.click(within(list).getByText('Title of ckpt-full'))
    expect(screen.getByTestId('checkpoints-panel')).toHaveAttribute('data-view', 'detail')
    for (const section of ['checkpoint-findings', 'checkpoint-runs', 'checkpoint-files', 'checkpoint-questions', 'checkpoint-citations', 'checkpoint-notes']) {
      expect(screen.getByTestId(section)).toBeInTheDocument()
    }
    expect(screen.getByTestId('checkpoint-notes')).toHaveTextContent('Finish the panel tab')
    expect(window.location.search).toBe(ADDRESS.slice(1))

    fireEvent.click(screen.getByText('All checkpoints'))
    expect(screen.getByTestId('checkpoints-panel')).toHaveAttribute('data-view', 'list')

    fireEvent.click(screen.getByTestId('panel-tab-close-checkpoints'))
    expect(screen.queryByTestId('panel-tab-checkpoints')).toBeNull()
  })
})

describe('single-checkpoint-links (FR-10)', () => {
  it('a conversation address carrying a checkpoint opens the Checkpoints tab on it, once', () => {
    const consumed = vi.fn()
    const view = renderThread({ checkpoint: 'ckpt-full', onCheckpointConsumed: consumed })
    expect(rowIds()).toEqual(['panel-tab-checkpoints'])
    expect(screen.getByTestId('checkpoint-detail-title')).toHaveTextContent('Title of ckpt-full')
    expect(consumed).toHaveBeenCalledTimes(1)

    // The host drops it from the address; nothing reopens after the operator closes the tab.
    fireEvent.click(screen.getByTestId('panel-tab-close-checkpoints'))
    view.rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ConversationView
          agent={AGENT}
          conversationId="conv-1"
          projectId={PROJECT_ID}
          document={null}
          checkpoint={null}
          onCheckpointConsumed={consumed}
          onSelectConversation={() => {}}
          onOpenDocument={() => {}}
          onBackToProject={() => {}}
          onOpenAgentSettings={() => {}}
        />
      </QueryClientProvider>,
    )
    expect(screen.queryByTestId('panel-tab-checkpoints')).toBeNull()
    expect(consumed).toHaveBeenCalledTimes(1)
  })

  it('the list form opens the tab on the thread’s list', () => {
    renderThread({ checkpoint: 'all', onCheckpointConsumed: () => {} })
    expect(screen.getByTestId('checkpoints-panel')).toHaveAttribute('data-view', 'list')
  })
})
