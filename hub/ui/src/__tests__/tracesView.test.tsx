/**
 * Activity → Traces, grouping and statistics (a-traces-view-with-filters-grouping-and-stats,
 * FR-5..FR-8, FR-14). Fed through `fetch` with the shapes `GET /traces` and `GET /traces/totals`
 * return: the list newest first and one page of it, the totals over every run the filter matches,
 * the groups in the order the Hub sorted them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { TraceGroup, TraceTotals } from '@/api/traces'
import { useConfigStore } from '@/store/configStore'
import { TracesPage } from '@/components/traces/TracesPage'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'alpha' }, { name: 'beta' }] }),
}))

const fetchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function totals(partial: Partial<TraceTotals>): TraceTotals {
  return {
    count: 0,
    errors: 0,
    error_kinds: { failed: 0, stopped: 0, trace_error: 0 },
    running: 0,
    cost_usd_micros: null,
    priced: 0,
    unpriced: 0,
    duration_seconds: 0,
    duration_avg_seconds: null,
    tokens: null,
    model_calls: 0,
    tool_calls: 0,
    tool_errors: 0,
    wait_seconds: 0,
    ...partial,
  }
}

function group(key: string, label: string, partial: Partial<TraceTotals>, extra: Partial<TraceGroup> = {}): TraceGroup {
  return { key, label, detail: null, missing: false, totals: totals(partial), ...extra }
}

function run(n: number, partial: Record<string, unknown> = {}) {
  const start = new Date(Date.UTC(2026, 10, 3, 3, 0, 0) - n * 60_000)
  return {
    trace_id: `tr-${n}`,
    root_span_id: `s-${n}`,
    run_id: `run-${n}`,
    name: 'invoke_agent',
    operation: 'invoke_agent',
    kind: 'run',
    agent: 'alpha',
    conversation_id: null,
    task_id: null,
    run_status: 'completed',
    status: 'ok',
    status_message: null,
    start_time: start.toISOString(),
    end_time: new Date(start.getTime() + 10_000).toISOString(),
    ended: true,
    span_count: 3,
    model: 'claude-haiku-5-5',
    task_ref: null,
    task_title: null,
    task_missing: false,
    conversation_title: null,
    cost_usd: 0.1,
    cost_state: 'measured',
    is_error: false,
    ...partial,
  }
}

// The five runs of headline-numbers: costs $0.10..$0.50, durations 10..50 s.
const FIVE = totals({
  count: 5,
  errors: 3,
  error_kinds: { failed: 1, stopped: 1, trace_error: 1 },
  cost_usd_micros: 1_500_000,
  priced: 5,
  duration_seconds: 150,
  duration_avg_seconds: 30,
  tokens: { input: 107, output: 23, cache_read: 300, cache_write: 41 },
  model_calls: 4,
  tool_calls: 5,
  wait_seconds: 12,
})

type Answer = { totals: TraceTotals; groups: TraceGroup[] | null }
let totalsFor: (groupBy: string | null) => Answer
let listed: () => { traces: unknown[]; next_before: string | null }

function urls(path: RegExp): URL[] {
  return fetchMock.mock.calls.map(([url]) => new URL(String(url))).filter((u) => path.test(u.pathname))
}
const totalsUrls = () => urls(/\/traces\/totals$/)

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub.test', isConfigured: true, selectedProjectId: 'proj-a' })
  totalsFor = () => ({ totals: FIVE, groups: null })
  listed = () => ({ traces: [run(0), run(1), run(2), run(3), run(4)], next_before: null })
  fetchMock.mockImplementation(async (url: string) => {
    const u = new URL(url)
    if (u.pathname.endsWith('/traces/totals')) {
      const groupBy = u.searchParams.get('group_by')
      return { ok: true, status: 200, json: async () => ({ ...totalsFor(groupBy), group_by: groupBy }) }
    }
    if (u.pathname.endsWith('/traces')) return { ok: true, status: 200, json: async () => listed() }
    return { ok: false, status: 404, json: async () => ({ detail: 'not here' }) }
  })
})
afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe('TracesPage statistics', () => {
  it('shows cost, duration and errors first, before any other statistic (headline-numbers)', async () => {
    render(<TracesPage />, { wrapper })
    const section = await screen.findByTestId('traces-totals')
    expect(within(section).getByTestId('traces-total-cost')).toHaveTextContent('$1.50')
    expect(screen.getByTestId('traces-total-duration')).toHaveTextContent('2m 30s')
    expect(screen.getByTestId('traces-average-duration')).toHaveTextContent('30.0 s on average')
    expect(screen.getByTestId('traces-total-errors')).toHaveTextContent('3')
    expect(screen.getByTestId('traces-stat-errors')).toHaveTextContent('1 failed · 1 stopped · 1 ended in error')
    // The order on screen: the three headline tiles, then the quieter line.
    const order = Array.from(section.children).map((el) => el.getAttribute('data-testid'))
    expect(order).toEqual(['traces-stat-cost', 'traces-stat-duration', 'traces-stat-errors', 'traces-secondary'])
    // Asked of the Hub with the list's own filters, not computed from the page.
    expect(totalsUrls()[0]!.searchParams.get('operation')).toBe('invoke_agent')
    expect(totalsUrls()[0]!.searchParams.get('group_by')).toBeNull()
  })

  it('offers tokens, model and tool calls and waiting time, matching what was recorded (secondary-numbers)', async () => {
    render(<TracesPage />, { wrapper })
    const secondary = await screen.findByTestId('traces-secondary')
    expect(within(secondary).getByTestId('traces-tokens')).toHaveTextContent('130 tokens')
    expect(within(secondary).getByTestId('traces-tokens').getAttribute('title')).toContain('300 tokens read from cache')
    expect(within(secondary).getByTestId('traces-model-calls')).toHaveTextContent('4 model calls')
    expect(within(secondary).getByTestId('traces-tool-calls')).toHaveTextContent('5 tool calls')
    expect(within(secondary).getByTestId('traces-waiting')).toHaveTextContent('12.0 s waiting on you')
  })

  it('counts every matching run, not the page that is loaded (stats-beyond-the-page)', async () => {
    listed = () => ({ traces: Array.from({ length: 50 }, (_, n) => run(n)), next_before: 'cursor' })
    totalsFor = () => ({ totals: totals({ count: 60, cost_usd_micros: 6_000_000, priced: 60, errors: 3, error_kinds: { failed: 3, stopped: 0, trace_error: 0 } }), groups: null })
    render(<TracesPage />, { wrapper })
    expect(await screen.findAllByTestId('trace-row')).toHaveLength(50)
    await waitFor(() => expect(screen.getByTestId('traces-total-count')).toHaveTextContent('60 runs'))
    expect(screen.getByTestId('traces-total-cost')).toHaveTextContent('$6.00')
    expect(screen.getByTestId('traces-total-errors')).toHaveTextContent('3')
    expect(screen.getByTestId('traces-count')).toHaveTextContent('50 runs on this page of 60')
    // Paging the list does not re-ask the totals: they never depended on the page.
    const asked = totalsUrls().length
    fireEvent.click(screen.getByRole('button', { name: 'Older' }))
    await waitFor(() => expect(urls(/\/traces$/).slice(-1)[0]!.searchParams.get('before')).toBe('cursor'))
    expect(totalsUrls().length).toBe(asked)
    expect(totalsUrls().every((u) => !u.searchParams.has('before') && !u.searchParams.has('limit'))).toBe(true)
  })

  it('leaves unpriced runs out of the total and says so; running runs are neither (unpriced-shown)', async () => {
    listed = () => ({
      traces: [
        run(0, { cost_usd: 0.25 }),
        run(1, { cost_usd: 0.75 }),
        run(2, { cost_usd: null, cost_state: 'unpriced', conversation_id: 'conv-2' }),
        run(3, { cost_usd: null, cost_state: 'running', end_time: null, ended: false, run_status: 'running' }),
      ],
      next_before: null,
    })
    totalsFor = (groupBy) => ({
      totals: totals({ count: 4, cost_usd_micros: 1_000_000, priced: 2, unpriced: 1, running: 1, duration_seconds: 30, duration_avg_seconds: 10 }),
      groups:
        groupBy === 'conversation'
          ? [
              group('conv-1', 'Priced talk', { count: 2, cost_usd_micros: 1_000_000, priced: 2 }),
              group('conv-2', 'Unmeasured talk', { count: 1, unpriced: 1 }),
              group('conv-3', 'Live talk', { count: 1, running: 1 }),
            ]
          : null,
    })
    render(<TracesPage />, { wrapper })
    const rows = await screen.findAllByTestId('trace-row')
    expect(within(rows[2]!).getByTestId('trace-cost')).toHaveTextContent('unpriced')
    expect(within(rows[3]!).getByTestId('trace-cost')).toHaveTextContent('—')
    expect(rows[3]).not.toHaveTextContent('unpriced')
    await waitFor(() => expect(screen.getByTestId('traces-total-cost')).toHaveTextContent('$1.00'))
    expect(screen.getByTestId('traces-unpriced-note')).toHaveTextContent('1 unpriced run left out')

    fireEvent.click(screen.getByRole('radio', { name: 'Conversation' }))
    const groups = await screen.findAllByTestId('traces-group')
    expect(within(groups[0]!).getByTestId('traces-group-cost')).toHaveTextContent('$1.00')
    const unmeasured = within(groups[1]!).getByTestId('traces-group-cost')
    expect(unmeasured).toHaveTextContent('unpriced')
    expect(groups[1]).not.toHaveTextContent('$0.00')
    expect(within(groups[2]!).getByTestId('traces-group-cost')).toHaveTextContent('—')
    expect(groups[2]).not.toHaveTextContent('unpriced')
    // The ungrouped total still says one run is left out.
    expect(screen.getByTestId('traces-unpriced-note')).toHaveTextContent('1 unpriced run left out')
  })

  it('switches through every grouping; each regroups the same runs and the counts add up (grouping-switches)', async () => {
    const byGrouping: Record<string, TraceGroup[]> = {
      agent: [group('alpha', 'alpha', { count: 3, errors: 1 }), group('beta', 'beta', { count: 2 })],
      model: [group('claude-haiku-5-5', 'claude-haiku-5-5', { count: 4 }), group('claude-sonnet-5-5', 'claude-sonnet-5-5', { count: 1 })],
      task: [
        group('task-1', 'T-1', { count: 2 }, { detail: 'First' }),
        group('task-2', 'T-2', { count: 2 }, { detail: 'Second' }),
        group('task-gone', 'Task no longer exists', { count: 1 }, { missing: true }),
      ],
      conversation: [group('', 'No conversation', { count: 5 })],
      kind: [group('run', 'Agent runs', { count: 5 })],
      day: [group('2026-11-03', '2026-11-03', { count: 3 }), group('2026-11-02', '2026-11-02', { count: 2 })],
    }
    totalsFor = (groupBy) => ({ totals: FIVE, groups: groupBy ? byGrouping[groupBy]! : null })
    render(<TracesPage />, { wrapper })
    await screen.findByTestId('traces-totals')
    const switcher = screen.getByRole('radiogroup', { name: 'Group by' })
    expect(within(switcher).getAllByRole('radio').map((r) => r.textContent)).toEqual([
      'None', 'Agent', 'Model', 'Task', 'Conversation', 'Kind', 'Day',
    ])
    for (const [label, key] of [
      ['Agent', 'agent'], ['Model', 'model'], ['Task', 'task'], ['Conversation', 'conversation'], ['Kind', 'kind'], ['Day', 'day'],
    ] as const) {
      fireEvent.click(within(switcher).getByRole('radio', { name: label }))
      await waitFor(() => expect(screen.getByTestId('traces-groups')).toHaveAttribute('data-grouping', key))
      expect(totalsUrls().slice(-1)[0]!.searchParams.get('group_by')).toBe(key)
      const groups = await screen.findAllByTestId('traces-group')
      expect(groups.map((g) => g.getAttribute('data-key'))).toEqual(byGrouping[key]!.map((g) => g.key))
      const counts = groups.map((g) => Number(within(g).getByTestId('traces-group-count').textContent))
      expect(counts.reduce((a, b) => a + b, 0)).toBe(5)
      for (const g of groups) {
        expect(within(g).getByTestId('traces-group-cost')).toBeInTheDocument()
        expect(within(g).getByTestId('traces-group-duration')).toBeInTheDocument()
        expect(within(g).getByTestId('traces-group-errors')).toBeInTheDocument()
      }
      // The list of runs under the groups is the same filtered list throughout.
      expect(screen.getAllByTestId('trace-row')).toHaveLength(5)
    }
    // A task that is gone is named so, and offers no filter by its raw id.
    fireEvent.click(within(switcher).getByRole('radio', { name: 'Task' }))
    const gone = (await screen.findAllByTestId('traces-group')).find((g) => g.getAttribute('data-key') === 'task-gone')!
    expect(gone).toHaveTextContent('Task no longer exists')
    expect(gone).not.toHaveTextContent('task-gone')
    expect(within(gone).queryByRole('button', { name: 'Only this' })).toBeNull()

    fireEvent.click(within(switcher).getByRole('radio', { name: 'None' }))
    await waitFor(() => expect(screen.queryByTestId('traces-groups')).toBeNull())
  })

  it('narrows to one group with Only this, keeping the grouping', async () => {
    totalsFor = (groupBy) => ({
      totals: FIVE,
      groups: groupBy === 'agent' ? [group('alpha', 'alpha', { count: 3 }), group('beta', 'beta', { count: 2 })] : null,
    })
    render(<TracesPage />, { wrapper })
    await screen.findByTestId('traces-totals')
    fireEvent.click(screen.getByRole('radio', { name: 'Agent' }))
    const beta = (await screen.findAllByTestId('traces-group'))[1]!
    fireEvent.click(within(beta).getByRole('button', { name: 'Only this' }))
    await waitFor(() => expect(totalsUrls().slice(-1)[0]!.searchParams.get('agent')).toBe('beta'))
    expect(totalsUrls().slice(-1)[0]!.searchParams.get('group_by')).toBe('agent')
    expect(urls(/\/traces$/).slice(-1)[0]!.searchParams.get('agent')).toBe('beta')
    expect(screen.getByTestId('traces-filter-agent')).toHaveValue('beta')
  })
})
