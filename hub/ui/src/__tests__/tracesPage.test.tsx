/**
 * Activity → Traces (a-traces-view-with-filters-grouping-and-stats). Driven through `fetch` with the
 * list in the order the route returns it: newest first. The first row is the newest run, so a list
 * that reversed or re-sorted it would fail here.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { TracesPage } from '@/components/traces/TracesPage'
import { ActivityScreen } from '@/components/activity/ActivityScreen'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'alpha' }, { name: 'beta' }] }),
}))
vi.mock('@/components/traces/ConversationTraceDrawer', () => ({
  ConversationTraceDrawer: ({ open, conversationId }: { open: boolean; conversationId: string }) =>
    open ? <div data-testid="conversation-trace-drawer" data-conversation-id={conversationId} /> : null,
}))
vi.mock('@/components/activity/ProjectLedger', () => ({ ProjectLedger: () => <div data-testid="ledger-stub" /> }))
vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div data-testid="logs-stub" /> }))

const fetchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function run(partial: Record<string, unknown>) {
  return {
    trace_id: `tr-${partial.run_id}`,
    root_span_id: 's',
    name: 'invoke_agent',
    operation: 'invoke_agent',
    kind: 'run',
    agent: 'alpha',
    conversation_id: null,
    task_id: null,
    run_status: 'completed',
    status: 'ok',
    status_message: null,
    start_time: '2026-11-03T01:00:00+00:00',
    end_time: '2026-11-03T01:00:10+00:00',
    ended: true,
    span_count: 3,
    model: 'claude-haiku-4-5',
    task_ref: null,
    task_title: null,
    task_missing: false,
    conversation_title: null,
    cost_usd: 0.012,
    cost_state: 'measured',
    is_error: false,
    ...partial,
  }
}

// Newest first, as the route returns them.
const RUNS = [
  run({ run_id: 'run-task', start_time: '2026-11-03T03:00:00+00:00', end_time: '2026-11-03T03:00:20+00:00', task_id: 'task-1', task_ref: 'T-7', task_title: 'Wire it', run_status: 'failed', status: 'error', is_error: true }),
  run({ run_id: 'run-conv', start_time: '2026-11-03T02:00:00+00:00', conversation_id: 'conv-1', conversation_title: 'Planning chat' }),
  run({ run_id: 'run-gone', start_time: '2026-11-03T01:30:00+00:00', task_id: 'task-b9bf0f35c2c5', task_missing: true, cost_usd: null, cost_state: 'unpriced' }),
  run({ run_id: 'run-live', start_time: '2026-11-03T01:00:00+00:00', end_time: null, ended: false, run_status: 'running', cost_usd: null, cost_state: 'running' }),
]

const requestTrace = {
  ...run({ run_id: null, trace_id: 'tr-req', name: 'POST /tasks', operation: 'aw.request', kind: 'request', agent: null, model: null }),
  cost_state: undefined,
  cost_usd: undefined,
}

function listedUrls(): URL[] {
  return fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => /\/traces\?/.test(url)).map((url) => new URL(url))
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub.test', isConfigured: true, selectedProjectId: 'proj-a' })
  fetchMock.mockImplementation(async (url: string) => {
    const u = new URL(url)
    if (u.pathname.includes('/traces/by-run/')) {
      return { ok: false, status: 404, json: async () => ({ detail: 'This run has no trace' }) }
    }
    const operation = u.searchParams.get('operation')
    const traces = operation === 'aw.request' ? [requestTrace] : RUNS
    return { ok: true, status: 200, json: async () => ({ traces, next_before: null }) }
  })
})
afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('TracesPage', () => {
  it('is a fourth view in Activity, beside Ledger, Activity and Logs', async () => {
    render(<ActivityScreen onOpenTask={vi.fn()} initialView="traces" />, { wrapper })
    expect(await screen.findByTestId('traces-view')).toBeInTheDocument()
    const group = screen.getByRole('radiogroup', { name: 'Activity view' })
    expect(within(group).getAllByRole('radio').map((r) => r.textContent)).toEqual(['Ledger', 'Activity', 'Logs', 'Traces'])
  })

  it('opens on agents’ runs only, and the Hub’s kinds sit behind Hub internals with a way back', async () => {
    render(<TracesPage />, { wrapper })
    await screen.findAllByTestId('trace-row')
    expect(listedUrls()[0]!.searchParams.get('operation')).toBe('invoke_agent')
    // The Hub's kinds are not beside the run filters: only inside the Hub internals choice.
    const filters = screen.getByRole('group', { name: 'Trace filters' })
    const internals = within(filters).getByLabelText('Hub internals')
    expect(within(filters).queryByText('Requests', { selector: ':not(option)' })).toBeNull()
    expect(within(internals).getByRole('option', { name: 'Requests' })).toBeInTheDocument()
    expect(screen.queryByTestId('traces-internal-note')).toBeNull()

    fireEvent.change(internals, { target: { value: 'request' } })
    await waitFor(() => expect(listedUrls().slice(-1)[0]!.searchParams.get('operation')).toBe('aw.request'))
    const rows = await screen.findAllByTestId('trace-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveAttribute('data-trace-id', 'tr-req')
    const note = screen.getByTestId('traces-internal-note')
    expect(note).toHaveTextContent('requests')
    fireEvent.click(within(note).getByRole('button', { name: 'Back to agent runs' }))
    await waitFor(() => expect(screen.getAllByTestId('trace-row')).toHaveLength(4))
    expect(listedUrls().slice(-1)[0]!.searchParams.get('operation')).toBe('invoke_agent')
  })

  it('sends every filter, alone and together, to the route', async () => {
    render(<TracesPage />, { wrapper })
    await screen.findAllByTestId('trace-row')
    fireEvent.change(screen.getByTestId('traces-filter-agent'), { target: { value: 'alpha' } })
    await waitFor(() => expect(listedUrls().slice(-1)[0]!.searchParams.get('agent')).toBe('alpha'))
    fireEvent.change(screen.getByTestId('traces-filter-range'), { target: { value: '1h' } })
    await waitFor(() => expect(listedUrls().slice(-1)[0]!.searchParams.get('since')).not.toBeNull())
    fireEvent.change(screen.getByTestId('traces-filter-task'), { target: { value: 'T-7' } })
    fireEvent.change(screen.getByTestId('traces-filter-conversation'), { target: { value: 'conv-1' } })
    fireEvent.change(screen.getByTestId('traces-filter-run'), { target: { value: 'run-task' } })
    await waitFor(() => {
      const q = listedUrls().slice(-1)[0]!.searchParams
      expect([q.get('agent'), q.get('task_id'), q.get('conversation_id'), q.get('run_id'), q.get('operation')]).toEqual([
        'alpha', 'T-7', 'conv-1', 'run-task', 'invoke_agent',
      ])
      expect(q.get('since')).not.toBeNull()
    })
    // One day: from the day's start to the next day's start.
    fireEvent.change(screen.getByTestId('traces-filter-day'), { target: { value: '2026-11-02' } })
    await waitFor(() => {
      const q = listedUrls().slice(-1)[0]!.searchParams
      const span = new Date(q.get('until')!).getTime() - new Date(q.get('since')!).getTime()
      expect(span).toBeGreaterThanOrEqual(23 * 3600_000)
      expect(span).toBeLessThanOrEqual(25 * 3600_000)
    })
  })

  it('shows each row’s fields, in the order the route returned them', async () => {
    render(<TracesPage />, { wrapper })
    const rows = await screen.findAllByTestId('trace-row')
    expect(rows.map((r) => r.getAttribute('data-run-id'))).toEqual(['run-task', 'run-conv', 'run-gone', 'run-live'])

    const [task, conv, gone, live] = rows as [HTMLElement, HTMLElement, HTMLElement, HTMLElement]
    expect(task).toHaveTextContent('alpha')
    expect(task).toHaveTextContent('claude-haiku-4-5')
    expect(task).toHaveTextContent('T-7')
    expect(task).toHaveTextContent('Wire it')
    expect(task).toHaveTextContent('20.0 s')
    expect(task).toHaveTextContent('$0.01')
    expect(task).toHaveAttribute('data-error', 'true')
    expect(task).toHaveTextContent('error')

    expect(conv).toHaveTextContent('Conversation turn')
    expect(conv).toHaveTextContent('Planning chat')
    expect(conv).toHaveAttribute('data-error', 'false')

    expect(gone).toHaveTextContent('Task no longer exists')
    expect(gone).not.toHaveTextContent('task-b9bf0f35c2c5')
    expect(within(gone).getByTestId('trace-cost')).toHaveTextContent('unpriced')
    expect(gone).not.toHaveTextContent('$0.00')

    expect(within(live).getByTestId('trace-cost')).toHaveTextContent('—')
    expect(live).not.toHaveTextContent('unpriced')
    expect(live).toHaveTextContent('running')
  })

  it('opens the run from anywhere on its row, adds no filter, and keeps the filters on return', async () => {
    render(<TracesPage />, { wrapper })
    await screen.findAllByTestId('trace-row')
    fireEvent.change(screen.getByTestId('traces-filter-agent'), { target: { value: 'alpha' } })
    await waitFor(() => expect(listedUrls().slice(-1)[0]!.searchParams.get('agent')).toBe('alpha'))
    const before = listedUrls().length

    const row = (await screen.findAllByTestId('trace-row'))[0]!
    fireEvent.click(within(row).getByText('Wire it'))
    const detail = await screen.findByTestId('trace-detail')
    expect(detail).toHaveAttribute('data-run-id', 'run-task')
    expect(listedUrls().length).toBe(before) // choosing the row text narrowed nothing
    expect(screen.getByTestId('traces-filter-task')).toHaveValue('')

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('trace-detail')).toBeNull())
    expect(screen.getByTestId('traces-filter-agent')).toHaveValue('alpha')
  })

  it('narrows to a row’s task only through its own control', async () => {
    render(<TracesPage />, { wrapper })
    const row = (await screen.findAllByTestId('trace-row'))[0]!
    fireEvent.click(within(row).getByRole('button', { name: 'Only runs of T-7' }))
    await waitFor(() => expect(listedUrls().slice(-1)[0]!.searchParams.get('task_id')).toBe('task-1'))
    expect(screen.queryByTestId('trace-detail')).toBeNull()
  })

  it('offers to open a conversation as one trace only while narrowed to a conversation that has runs', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      const u = new URL(url)
      const conv = u.searchParams.get('conversation_id')
      const traces = conv === 'conv-1' ? RUNS.filter((r) => r.conversation_id === 'conv-1') : conv ? [] : RUNS
      return { ok: true, status: 200, json: async () => ({ traces, next_before: null, totals: null }) }
    })
    render(<TracesPage />, { wrapper })
    await screen.findAllByTestId('trace-row')
    expect(screen.queryByTestId('traces-open-conversation-trace')).toBeNull()

    fireEvent.change(screen.getByTestId('traces-filter-conversation'), { target: { value: 'conv-none' } })
    await screen.findByText('No traces match.')
    expect(screen.queryByTestId('traces-open-conversation-trace')).toBeNull()

    fireEvent.change(screen.getByTestId('traces-filter-conversation'), { target: { value: 'conv-1' } })
    fireEvent.click(await screen.findByTestId('traces-open-conversation-trace'))
    expect(screen.getByTestId('conversation-trace-drawer')).toHaveAttribute('data-conversation-id', 'conv-1')
  })
})
