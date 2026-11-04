import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ProjectCheckpoint, ProjectCheckpointList } from '@/api/checkpoints'
import { CheckpointsPage, type CheckpointsPageProps } from '@/components/checkpoints/CheckpointsPage'
import { CheckpointsScreen } from '@/components/checkpoints/CheckpointsScreen'
import { NO_FILTERS, statusWords, triggerWords } from '@/components/checkpoints/checkpointModel'
import { checkpointsDestination, parseDestination, serializeDestination, type ProjectTabDestination } from '@/lib/navigation'
import { useConfigStore } from '@/store/configStore'
import { chooseMenuOption } from './support/menuSelect'

const getJson = vi.fn()
vi.mock('@/api/client', () => ({
  getJson: (path: string) => getJson(path),
  postJson: vi.fn(),
  readableApiError: (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback),
}))
vi.mock('@/hooks/useSSE', () => ({ useSSE: () => undefined }))
vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: [{ name: 'Builder' }, { name: 'QA' }] }) }
})
vi.mock('@/api/agentChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agentChat')>()
  const conversation = (id: string, agent: string, title: string, lifecycle: 'open' | 'archived') => ({
    id, agent, title, lifecycle,
  })
  return {
    ...actual,
    useProjectConversations: (_: string | null, lifecycle: 'open' | 'archived' = 'open') => ({
      data: {
        conversations:
          lifecycle === 'open'
            ? [conversation('conv-b2', 'Builder', 'Wire the tab', 'open'), conversation('conv-q1', 'QA', 'Review the fill', 'open')]
            : [conversation('conv-b1', 'Builder', 'Routes work', 'archived')],
      },
    }),
  }
})
// The trace drawer is the app's own and has its own tests; here only that each run opens its trace.
vi.mock('@/components/traces/TraceDrawer', () => ({
  TraceButton: ({ runId, testId }: { runId?: string; testId?: string }) => (
    <button type="button" data-testid={testId} data-run-id={runId}>
      Open trace
    </button>
  ),
}))

const BODY = '## Objective\n\nShip the tab.\n\n- first item\n- second item\n'

function checkpoint(over: Partial<ProjectCheckpoint> & { id: string }): ProjectCheckpoint {
  return {
    conversation_id: 'conv-b2',
    agent: 'Builder',
    trigger: 'operator',
    status: 'ready',
    lineage_id: over.id,
    title: `Title of ${over.id}`,
    summary: `Summary of ${over.id}`,
    body: BODY,
    created_at: '2026-10-17T12:00:00Z',
    covered_runs: [],
    ...over,
  }
}

function page(over: Partial<CheckpointsPageProps> = {}) {
  const props: CheckpointsPageProps = {
    checkpoints: [],
    lineage: null,
    filters: NO_FILTERS,
    onFilters: vi.fn(),
    agents: ['Builder', 'QA'],
    conversations: [{ id: 'conv-b2', label: 'Wire the tab' }],
    conversationLabel: (id) => (id === 'conv-b2' ? 'Wire the tab' : 'Another conversation'),
    selectedId: null,
    onSelect: vi.fn(),
    now: new Date('2026-10-17T13:00:00Z'),
    ...over,
  }
  return { props, ...render(<CheckpointsPage {...props} />) }
}

describe('the Checkpoints list', () => {
  it('lists the checkpoints in the order the route returns them, newest first (FR-1)', () => {
    page({
      checkpoints: [
        checkpoint({ id: 'ckpt-new', created_at: '2026-10-17T12:00:00Z' }),
        checkpoint({ id: 'ckpt-old', created_at: '2026-10-16T12:00:00Z' }),
      ],
    })
    const rows = within(screen.getByTestId('checkpoints-list')).getAllByRole('button')
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual(['checkpoint-row-ckpt-new', 'checkpoint-row-ckpt-old'])
  })

  it('shows title, summary, agent, trigger, time, status and conversation on each row (FR-2)', () => {
    page({ checkpoints: [checkpoint({ id: 'ckpt-1', agent: 'QA', trigger: 'task_completion' })] })
    const row = screen.getByTestId('checkpoint-row-ckpt-1')
    expect(within(row).getByTestId('checkpoint-row-title')).toHaveTextContent('Title of ckpt-1')
    expect(within(row).getByTestId('checkpoint-row-summary')).toHaveTextContent('Summary of ckpt-1')
    expect(within(row).getByTestId('checkpoint-row-agent')).toHaveTextContent('QA')
    expect(within(row).getByTestId('checkpoint-row-trigger')).toHaveTextContent('A task finished')
    expect(within(row).getByTestId('checkpoint-row-time')).toHaveTextContent(/Oct 17/)
    expect(within(row).getByTestId('checkpoint-row-status')).toHaveTextContent('Ready')
    expect(within(row).getByTestId('checkpoint-row-conversation')).toHaveTextContent('Wire the tab')
  })

  it('uses no internal word for any trigger or status, listed or opened (FR-3)', () => {
    const triggers = ['task_completion', 'operator', 'context_pressure']
    const statuses = ['ready', 'unwritten', 'failed']
    const rows = triggers.flatMap((trigger, t) =>
      statuses.map((status, s) =>
        checkpoint({
          id: `ckpt-${t}-${s}`,
          trigger,
          status: status as ProjectCheckpoint['status'],
          probe_status: status === 'failed' ? 'failed' : 'passed',
          probe_findings: status === 'failed' ? [{ dimension: 'files', missing: ['a.py'], invented: [] }] : null,
        }),
      ),
    )
    const { rerender, props } = page({ checkpoints: rows })
    const forbidden = /task_completion|context_pressure|unwritten|probe/i
    expect(screen.getByTestId('checkpoints-page').textContent).not.toMatch(forbidden)
    for (const row of rows) {
      rerender(<CheckpointsPage {...props} selectedId={row.id} />)
      expect(screen.getByTestId('checkpoint-detail').textContent).not.toMatch(forbidden)
    }
    expect(triggerWords('operator')).toBe('The operator asked')
    expect(triggerWords('context_pressure')).toBe('The conversation grew long')
    expect(statusWords('unwritten').label).toBe('Nothing was written')
  })

  it('shows a readable trigger for a value it has no wording for', () => {
    page({ checkpoints: [checkpoint({ id: 'ckpt-x', trigger: 'handoff_requested' })] })
    expect(screen.getByTestId('checkpoint-row-trigger')).toHaveTextContent('Handoff requested')
    expect(triggerWords('')).not.toBe('')
  })

  it('narrows with the controls, and offers to show everything again (FR-4)', async () => {
    const onFilters = vi.fn()
    const user = userEvent.setup()
    page({ onFilters })
    await chooseMenuOption(user, 'Agent', 'QA')
    expect(onFilters).toHaveBeenLastCalledWith({ agent: 'QA', trigger: '', conversationId: '' })
    await chooseMenuOption(user, 'What triggered it', 'The operator asked')
    expect(onFilters).toHaveBeenLastCalledWith({ agent: '', trigger: 'operator', conversationId: '' })
  })

  it('says when nothing matches, instead of an empty list', () => {
    page({ filters: { agent: 'QA', trigger: '', conversationId: '' } })
    expect(screen.getByTestId('checkpoints-empty')).toHaveTextContent('No checkpoint matches')
    expect(screen.getByTestId('checkpoints-clear-filters')).toBeInTheDocument()
  })
})

describe('an opened checkpoint', () => {
  it('renders its body as formatted text (FR-6)', () => {
    page({ checkpoints: [checkpoint({ id: 'c1' })], selectedId: 'c1' })
    const body = screen.getByTestId('checkpoint-body')
    expect(within(body).getByRole('heading', { name: 'Objective' })).toBeInTheDocument()
    expect(within(body).getAllByRole('listitem')).toHaveLength(2)
    expect(body.textContent).not.toContain('## ')
  })

  it('names every run it covers and opens each run’s trace (FR-7)', () => {
    const runs = ['run-1', 'run-2', 'run-3'].map((id) => ({
      run_id: id, agent: 'Builder', status: 'completed', started_at: '2026-10-17T10:00:00Z', ended_at: null,
    }))
    page({ checkpoints: [checkpoint({ id: 'c1', covered_runs: runs })], selectedId: 'c1' })
    const section = screen.getByTestId('checkpoint-runs')
    expect(within(section).getAllByRole('listitem')).toHaveLength(3)
    expect(section).toHaveTextContent('Run 1')
    expect(section).toHaveTextContent('Run 3')
    for (const id of ['run-1', 'run-2', 'run-3']) {
      expect(screen.getByTestId(`checkpoint-run-trace-${id}`)).toHaveAttribute('data-run-id', id)
    }
  })

  it('says it covers no recorded run when it records none', () => {
    page({ checkpoints: [checkpoint({ id: 'c1', covered_runs: [] })], selectedId: 'c1' })
    expect(screen.getByTestId('checkpoint-no-runs')).toHaveTextContent('covers no recorded run')
  })

  it('shows files, questions, citations and carried notes only when present (FR-8)', () => {
    const full = checkpoint({
      id: 'full',
      files_changed: ['a.py'],
      open_questions: [{ id: 'q', question: 'Which one?' }],
      citations: [{ id: 'c', preview: 'The operator said so.' }],
    })
    const { rerender, props } = page({
      checkpoints: [full],
      selectedId: 'full',
      notes: [{
        id: 'n', agent: 'Builder', run_id: null, intent: 'Keep the order.', suspicions: [], warnings: [],
        consumed_by_checkpoint_id: 'full', created_at: null,
      }],
    })
    for (const id of ['checkpoint-files', 'checkpoint-questions', 'checkpoint-citations', 'checkpoint-notes']) {
      expect(screen.getByTestId(id)).toBeInTheDocument()
    }
    const bare = checkpoint({ id: 'bare' })
    rerender(<CheckpointsPage {...props} checkpoints={[bare]} selectedId="bare" notes={[]} />)
    for (const heading of ['Files changed', 'Open questions', 'Cited', 'Notes the agent left']) {
      expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument()
    }
  })

  it('marks a title the Hub made and says why, offering what the model returned (FR-9)', async () => {
    const onShowRaw = vi.fn()
    const user = userEvent.setup()
    const fromBody = checkpoint({
      id: 'body', title_made_by: 'hub_from_body', title_reason: 'Both answers lacked a title.',
    })
    const fromFacts = checkpoint({
      id: 'facts', title_made_by: 'hub_from_facts', title_reason: 'Neither answer could be read.',
      has_unreadable_answer: true, body: null,
    })
    const probed = checkpoint({
      id: 'probed', status: 'failed',
      probe_findings: [{ dimension: 'files_changed', missing: ['hub/x.py'], invented: ['hub/y.py'] }],
    })
    const { rerender, props } = page({ checkpoints: [fromBody, fromFacts, probed], selectedId: 'body', onShowRaw })
    expect(screen.getAllByTestId(/checkpoint-row-/).length).toBeGreaterThanOrEqual(3)
    expect(screen.getByTestId('checkpoint-made-by-hub')).toBeInTheDocument()
    expect(screen.getByTestId('checkpoint-why')).toHaveTextContent('Both answers lacked a title.')
    expect(screen.queryByText('Show what the model returned')).not.toBeInTheDocument()

    rerender(<CheckpointsPage {...props} selectedId="facts" onShowRaw={onShowRaw} />)
    expect(screen.getByTestId('checkpoint-why')).toHaveTextContent('Neither answer could be read.')
    await user.click(screen.getByText('Show what the model returned'))
    expect(onShowRaw).toHaveBeenCalledWith('facts')
    // The raw text is never the body.
    expect(screen.getByTestId('checkpoint-detail')).toHaveTextContent('has no written text')
    rerender(<CheckpointsPage {...props} selectedId="facts" rawAnswer="plain prose the model sent" />)
    expect(screen.getByTestId('checkpoint-raw-answer')).toHaveTextContent('plain prose the model sent')

    rerender(<CheckpointsPage {...props} selectedId="probed" />)
    expect(screen.getByTestId('checkpoint-findings')).toHaveTextContent('missing hub/x.py')
    expect(screen.getByTestId('checkpoint-findings')).toHaveTextContent('invented hub/y.py')
  })

  it('shows the lineage both ways (FR-10)', async () => {
    const onSelect = vi.fn()
    const onOpenConversation = vi.fn()
    const user = userEvent.setup()
    const successor = checkpoint({
      id: 'succ',
      carried_from: { checkpoint_id: 'ckpt-c', conversation_id: 'conv-b1', title: 'The source checkpoint' },
    })
    const predecessor = checkpoint({
      id: 'pred', conversation_id: 'conv-b1',
      cut_over_to_conversation_id: 'conv-b2', carried_into: { conversation_id: 'conv-b2' },
    })
    const { rerender, props } = page({ checkpoints: [successor, predecessor], selectedId: 'succ', onSelect, onOpenConversation })
    await user.click(within(screen.getByTestId('checkpoint-detail-lineage')).getByText('The source checkpoint'))
    expect(onSelect).toHaveBeenCalledWith('ckpt-c')

    rerender(<CheckpointsPage {...props} selectedId="pred" onSelect={onSelect} onOpenConversation={onOpenConversation} />)
    await user.click(within(screen.getByTestId('checkpoint-detail-lineage')).getByText('Wire the tab'))
    expect(onOpenConversation).toHaveBeenCalledWith(null, 'conv-b2')
  })

  it('states where a conversation with no checkpoints of its own came from', () => {
    page({
      checkpoints: [],
      filters: { agent: '', trigger: '', conversationId: 'conv-b2' },
      lineage: {
        conversation_id: 'conv-b2',
        started_from: { checkpoint_id: 'ckpt-c', conversation_id: 'conv-b1', title: 'The source checkpoint' },
        carried_into: null,
      },
    })
    expect(screen.getByTestId('checkpoints-started-from')).toHaveTextContent('started from The source checkpoint')
  })
})

describe('the Checkpoints address', () => {
  it('round-trips an opened checkpoint and its narrowing, apart from the conversation parameters', () => {
    const destination = checkpointsDestination('proj-1', {
      checkpoint: 'ckpt-1', agent: 'Builder', trigger: 'operator', conversation: 'conv-b2',
    })
    const search = serializeDestination(destination)
    const params = new URLSearchParams(search)
    expect(params.get('tab')).toBe('checkpoints')
    expect(params.has('agent')).toBe(false)
    expect(params.has('conversation')).toBe(false)
    expect(parseDestination(search)).toEqual(destination)
  })

  it('drops a value that does not parse rather than failing', () => {
    expect(checkpointsDestination('proj-1', { checkpoint: '../x/..\n' })).toEqual({
      kind: 'project', projectId: 'proj-1', tab: 'checkpoints',
    })
  })
})

describe('the Checkpoints tab, wired to the route', () => {
  const ROWS: ProjectCheckpoint[] = [
    checkpoint({ id: 'b-op-new', agent: 'Builder', trigger: 'operator', conversation_id: 'conv-b2', created_at: '2026-10-17T12:00:00Z' }),
    checkpoint({ id: 'b-task', agent: 'Builder', trigger: 'task_completion', conversation_id: 'conv-b2', created_at: '2026-10-17T11:00:00Z' }),
    checkpoint({ id: 'q-op', agent: 'QA', trigger: 'operator', conversation_id: 'conv-q1', created_at: '2026-10-17T10:00:00Z' }),
    checkpoint({ id: 'b-op-old', agent: 'Builder', trigger: 'operator', conversation_id: 'conv-b1', created_at: '2026-10-16T10:00:00Z' }),
  ]

  /** The route as the Hub answers it: filtered, newest first. */
  function route(path: string): unknown {
    const url = new URL(path, 'http://hub')
    if (url.pathname.endsWith('/checkpoint-notes')) return { notes: [] }
    const agent = url.searchParams.get('agent')
    const trigger = url.searchParams.get('trigger')
    const conversation = url.searchParams.get('conversation_id')
    const checkpoints = ROWS.filter(
      (row) =>
        (!agent || row.agent === agent) &&
        (!trigger || row.trigger === trigger) &&
        (!conversation || row.conversation_id === conversation),
    )
    return { checkpoints, lineage: null } satisfies ProjectCheckpointList
  }

  function mount(destination: ProjectTabDestination) {
    const onNavigate = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={client}>
        <CheckpointsScreen destination={destination} onNavigate={onNavigate} onOpenConversation={vi.fn()} />
      </QueryClientProvider>,
    )
    return { onNavigate, ...view }
  }

  beforeEach(() => {
    getJson.mockReset()
    getJson.mockImplementation((path: string) => Promise.resolve(route(path)))
    useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1' })
  })

  it('lists every checkpoint with no narrowing, newest first, naming conversations by title', async () => {
    mount(checkpointsDestination('proj-1'))
    const list = await screen.findByTestId('checkpoints-list')
    expect(within(list).getAllByRole('button').map((row) => row.getAttribute('data-testid'))).toEqual(
      ROWS.map((row) => `checkpoint-row-${row.id}`),
    )
    expect(within(list).getAllByTestId('checkpoint-row-conversation').map((node) => node.textContent)).toEqual([
      'Wire the tab', 'Wire the tab', 'Review the fill', 'Routes work',
    ])
  })

  it('asks the route for the agent, trigger and conversation named in the address, combined (FR-4)', async () => {
    mount(checkpointsDestination('proj-1', { agent: 'Builder', trigger: 'operator', conversation: 'conv-b2' }))
    const list = await screen.findByTestId('checkpoints-list')
    expect(within(list).getAllByRole('button')).toHaveLength(1)
    const url = new URL(getJson.mock.calls.map((call) => call[0] as string).find((p) => p.includes('/checkpoints?'))!, 'http://hub')
    expect(url.searchParams.get('agent')).toBe('Builder')
    expect(url.searchParams.get('trigger')).toBe('operator')
    expect(url.searchParams.get('conversation_id')).toBe('conv-b2')
  })

  it('narrows to an agent, then to its operator-asked checkpoints, keeping the earlier narrowing', async () => {
    const user = userEvent.setup()
    const { onNavigate } = mount(checkpointsDestination('proj-1', { agent: 'Builder' }))
    await screen.findByTestId('checkpoints-list')
    expect(screen.queryByTestId('checkpoint-row-q-op')).not.toBeInTheDocument()
    await chooseMenuOption(user, 'What triggered it', 'The operator asked')
    expect(onNavigate).toHaveBeenLastCalledWith(
      checkpointsDestination('proj-1', { agent: 'Builder', trigger: 'operator' }),
    )
  })

  it('opens the checkpoint the address names, even when the narrowing hides it', async () => {
    mount(checkpointsDestination('proj-1', { agent: 'QA', checkpoint: 'b-task' }))
    expect(await screen.findByTestId('checkpoint-detail')).toHaveTextContent('Title of b-task')
    expect(screen.queryByTestId('checkpoint-row-b-task')).not.toBeInTheDocument()
  })

  it('carries a changed selection into the address', async () => {
    const { onNavigate } = mount(checkpointsDestination('proj-1', { agent: 'Builder' }))
    fireEvent.click(await screen.findByTestId('checkpoint-row-b-task'))
    await waitFor(() =>
      expect(onNavigate).toHaveBeenCalledWith(checkpointsDestination('proj-1', { agent: 'Builder', checkpoint: 'b-task' })),
    )
  })
})
