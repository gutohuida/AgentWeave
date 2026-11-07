/**
 * A trace of a whole conversation (a-trace-of-a-whole-conversation). The model is fed runs in the
 * order the list route returns them (newest first); the drawer is driven through `fetch`, so what
 * is requested, and when, is what the routes would see.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { Span, TraceDetail, TraceSummary } from '@/api/traces'
import { useConfigStore } from '@/store/configStore'
import { ConversationTraceDrawer } from '@/components/traces/ConversationTraceDrawer'
import {
  boundsOf,
  buildAxis,
  buildTimeline,
  conversationTotals,
  numberRuns,
  runFromSummary,
  selectRuns,
  withRouteTotals,
} from '@/components/traces/conversationTraceModel'

const MIN = 60_000
const T0 = Date.parse('2026-11-03T01:00:00Z')

function iso(ms: number): string {
  return new Date(ms).toISOString()
}

function row(id: string, startMs: number, durMs: number, extra: Partial<TraceSummary> = {}): TraceSummary {
  return {
    trace_id: `tr-${id}`,
    root_span_id: `root-${id}`,
    run_id: id,
    name: 'invoke_agent',
    operation: 'invoke_agent',
    kind: 'run',
    agent: 'alpha',
    conversation_id: 'conv-1',
    task_id: null,
    run_status: 'completed',
    initiator: 'autonomous',
    status: 'ok',
    status_message: null,
    start_time: iso(startMs),
    end_time: iso(startMs + durMs),
    ended: true,
    span_count: 2,
    model: 'claude-haiku-4-5',
    conversation_title: 'Planning chat',
    cost_usd: 0.01,
    cost_state: 'measured',
    is_error: false,
    ...extra,
  }
}

/** Newest first, as the list route returns them. */
function newestFirst(rows: TraceSummary[]): TraceSummary[] {
  return [...rows].sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time))
}

describe('the conversation trace model', () => {
  it('numbers the turns oldest first from rows the route returns newest first', () => {
    const rows = newestFirst([row('a', T0, 5 * MIN), row('b', T0 + 10 * MIN, 5 * MIN, { initiator: 'operator' }), row('c', T0 + 20 * MIN, 5 * MIN)])
    expect(rows.map((r) => r.run_id)).toEqual(['c', 'b', 'a'])
    const turns = numberRuns(rows.map(runFromSummary))
    expect(turns.map((r) => [r.turn, r.run_id])).toEqual([[1, 'a'], [2, 'b'], [3, 'c']])
    const axis = buildAxis(turns, T0 + 60 * MIN)
    const placed = buildTimeline(turns, {}, new Set(), axis, T0 + 60 * MIN)
    const starts = placed.map((p) => p.x0)
    expect(starts).toEqual([...starts].sort((x, y) => x - y))
    expect(starts[1]).toBeGreaterThan(starts[0]!)
    expect(starts[2]).toBeGreaterThan(starts[1]!)
  })

  it('folds a 9 hour gap into one break, keeps the short gap to scale and leaves the first turn wide', () => {
    const turns = numberRuns(
      [row('a', T0, 5 * MIN), row('b', T0 + 9 * 60 * MIN + 5 * MIN, 5 * MIN), row('c', T0 + 9 * 60 * MIN + 15 * MIN, 5 * MIN)].map(runFromSummary),
    )
    const axis = buildAxis(turns, T0 + 12 * 60 * MIN)
    const breaks = axis.segments.filter((s) => s.kind === 'break')
    expect(breaks).toHaveLength(1)
    expect(breaks[0]!.endMs - breaks[0]!.startMs).toBe(9 * 60 * MIN)
    const placed = buildTimeline(turns, {}, new Set(), axis, T0 + 12 * 60 * MIN)
    const [a, b, c] = placed
    expect(a!.x1 - a!.x0).toBeGreaterThan(0.1)
    expect(b!.x0).toBeGreaterThanOrEqual(breaks[0]!.x1)
    // b ends at +5 minutes, c starts 5 minutes after b ended: the gap is as wide as a turn.
    expect(c!.x0 - b!.x1).toBeCloseTo(b!.x1 - b!.x0, 6)
  })

  it('totals three turns of 1, 2 and 3 minutes, one unpriced and one failed', () => {
    const turns = numberRuns(
      [
        row('a', T0, 1 * MIN, { cost_usd: 0.5 }),
        row('b', T0 + 20 * MIN, 2 * MIN, { cost_usd: null, cost_state: 'unpriced' }),
        row('c', T0 + 59 * MIN, 3 * MIN, { cost_usd: 0.25, run_status: 'failed', status: 'error', is_error: true }),
      ].map(runFromSummary),
    )
    const t = conversationTotals(turns, T0 + 120 * MIN)
    expect(t.runs).toBe(3)
    expect(t.workingMs).toBe(6 * MIN)
    expect(t.elapsedMs).toBe(62 * MIN)
    expect(t.costUsdMicros).toBe(750_000)
    expect(t.priced).toBe(2)
    expect(t.unpriced).toBe(1)
    expect(t.failedRuns).toBe(1)
  })

  it('leaves a running turn neither priced nor unpriced', () => {
    const t = conversationTotals(
      numberRuns([row('a', T0, 0, { end_time: null, ended: false, cost_usd: null, cost_state: 'running' })].map(runFromSummary)),
      T0 + MIN,
    )
    expect(t.unpriced).toBe(0)
    expect(t.priced).toBe(0)
  })

  it('narrows to turns 9 to 12, and to a start time no turn has', () => {
    const turns = numberRuns(Array.from({ length: 24 }, (_, i) => runFromSummary(row(`r${i + 1}`, T0 + i * 30 * MIN, 5 * MIN))))
    const now = T0 + 30 * 60 * MIN
    expect(selectRuns(turns, { from: 9, to: 12, since: 'all' }, now).map((r) => r.turn)).toEqual([9, 10, 11, 12])
    expect(selectRuns(turns, { from: 1, to: 24, since: '1h' }, T0 + 400 * 60 * MIN)).toEqual([])
    const b = boundsOf(selectRuns(turns, { from: 9, to: 12, since: 'all' }, now))!
    expect(Date.parse(b.since)).toBe(T0 + 8 * 30 * MIN)
    expect(Date.parse(b.until)).toBe(T0 + 11 * 30 * MIN + 1000)
  })

  it('takes the Hub’s counts for the rows’ none, and says nothing while they are read', () => {
    const rows = conversationTotals(numberRuns([runFromSummary(row('a', T0, MIN))]), T0 + MIN)
    expect(withRouteTotals(rows, null).modelCalls).toBeNull()
    expect(withRouteTotals(rows, undefined).modelCalls).toBe(0)
  })
})

const fetchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function span(partial: Partial<Span> & Pick<Span, 'span_id' | 'start_time'>): Span {
  return {
    trace_id: 't',
    parent_span_id: null,
    name: partial.span_id,
    operation: 'chat',
    status: 'unset',
    status_message: null,
    end_time: null,
    ended: true,
    attributes: {},
    events: [],
    ...partial,
  }
}

function detailFor(r: TraceSummary): TraceDetail {
  const start = Date.parse(r.start_time)
  const end = Date.parse(r.end_time!)
  const rootSpan = span({ span_id: `root-${r.run_id}`, name: 'invoke_agent alpha', operation: 'invoke_agent', start_time: r.start_time, end_time: r.end_time })
  const chat = span({
    span_id: `chat-${r.run_id}`,
    parent_span_id: rootSpan.span_id,
    name: 'chat claude-haiku',
    start_time: iso(start + (end - start) / 2),
    end_time: iso(start + (end - start) * 0.75),
    attributes: { 'gen_ai.request.model': 'claude-haiku-4-5' },
  })
  return { trace_id: r.trace_id, kind: 'run', run_id: r.run_id, root: rootSpan, spans: [rootSpan, chat], total: 2, offset: 0, limit: 500 }
}

interface Hub {
  /** Rows per conversation, newest first. */
  runs: Record<string, TraceSummary[]>
  /** Run ids whose trace was cleared. */
  cleared: Set<string>
  earlier: Record<string, { conversation_id: string; title: string }>
}
let hub: Hub

function totalsFor(rows: TraceSummary[]) {
  const priced = rows.filter((r) => r.cost_state === 'measured')
  return {
    totals: {
      count: rows.length,
      errors: rows.filter((r) => r.is_error).length,
      error_kinds: { failed: rows.filter((r) => r.is_error).length, stopped: 0, trace_error: 0 },
      running: rows.filter((r) => !r.ended).length,
      cost_usd_micros: priced.length ? priced.reduce((s, r) => s + Math.round((r.cost_usd ?? 0) * 1e6), 0) : null,
      priced: priced.length,
      unpriced: rows.filter((r) => r.cost_state === 'unpriced').length,
      duration_seconds: rows.reduce((s, r) => s + (Date.parse(r.end_time ?? r.start_time) - Date.parse(r.start_time)) / 1000, 0),
      duration_avg_seconds: null,
      tokens: null,
      model_calls: rows.length * 2,
      tool_calls: rows.length,
      wait_seconds: 0,
    },
    group_by: null,
    groups: null,
  }
}

function paths(): URL[] {
  return fetchMock.mock.calls.map(([url]) => new URL(String(url)))
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub.test', isConfigured: true, selectedProjectId: 'proj-a' })
  hub = { runs: {}, cleared: new Set(), earlier: {} }
  fetchMock.mockImplementation(async (url: string) => {
    const u = new URL(url)
    const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
    if (u.pathname.endsWith('/checkpoints')) {
      const id = u.searchParams.get('conversation_id') ?? ''
      return ok({ checkpoints: [], lineage: { conversation_id: id, started_from: hub.earlier[id] ? { checkpoint_id: 'ck', ...hub.earlier[id] } : null, carried_into: null } })
    }
    if (u.pathname.includes('/traces/by-run/')) {
      const id = decodeURIComponent(u.pathname.split('/').pop()!)
      const found = Object.values(hub.runs).flat().find((r) => r.run_id === id)
      if (!found || hub.cleared.has(id)) return { ok: false, status: 404, json: async () => ({ detail: 'This run has no trace' }) }
      return ok(detailFor(found))
    }
    const conv = u.searchParams.get('conversation_id') ?? ''
    let rows = hub.runs[conv] ?? []
    const before = u.searchParams.get('before')
    const limit = Number(u.searchParams.get('limit') ?? 50)
    if (u.pathname.endsWith('/traces/totals')) {
      const since = u.searchParams.get('since')
      const until = u.searchParams.get('until')
      // A bound that is not an ISO instant is refused, as the Hub does.
      for (const bound of [since, until]) if (bound && Number.isNaN(Date.parse(bound))) return { ok: false, status: 422, json: async () => ({ detail: 'bad bound' }) }
      if (since) rows = rows.filter((r) => Date.parse(r.start_time) >= Date.parse(since))
      if (until) rows = rows.filter((r) => Date.parse(r.start_time) < Date.parse(until))
      return ok(totalsFor(rows))
    }
    if (before) rows = rows.slice(rows.findIndex((r) => r.run_id === before) + 1)
    const page = rows.slice(0, limit)
    const more = rows.length > limit
    return ok({ traces: page, next_before: more ? page[page.length - 1]!.run_id : null })
  })
})
afterEach(() => {
  cleanup()
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

function open(conversationId = 'conv-1') {
  return render(<ConversationTraceDrawer conversationId={conversationId} title="Planning chat" agent="alpha" open onOpenChange={() => undefined} />, { wrapper })
}

function byRunRequests(): URL[] {
  return paths().filter((u) => u.pathname.includes('/traces/by-run/'))
}

function turnsOf(n: number, step = 30 * MIN, extra: (i: number) => Partial<TraceSummary> = () => ({})): TraceSummary[] {
  return newestFirst(Array.from({ length: n }, (_, i) => row(`r${i + 1}`, T0 + i * step, 5 * MIN, { cost_usd: 0.1, ...extra(i) })))
}

describe('ConversationTraceDrawer', () => {
  it('numbers the turns oldest first from rows returned newest first and marks the ones you started', async () => {
    hub.runs['conv-1'] = newestFirst([row('a', T0, 5 * MIN, { initiator: 'operator' }), row('b', T0 + 10 * MIN, 5 * MIN), row('c', T0 + 20 * MIN, 5 * MIN)])
    open()
    const turns = await screen.findAllByTestId('conversation-turn')
    expect(turns.map((t) => [t.getAttribute('data-number'), t.getAttribute('data-run-id')])).toEqual([['1', 'a'], ['2', 'b'], ['3', 'c']])
    const lefts = turns.map((t) => Number(within(t).getByTestId('conversation-turn-bar').getAttribute('data-left')))
    expect(lefts[1]).toBeGreaterThan(lefts[0]!)
    expect(lefts[2]).toBeGreaterThan(lefts[1]!)
    expect(within(turns[0]!).getByTestId('conversation-turn-from-you')).toHaveTextContent('from you')
    expect(within(turns[1]!).queryByTestId('conversation-turn-from-you')).toBeNull()
  })

  it('draws one break labelled 9h 0m later, with the first turn wider than a tenth of the axis', async () => {
    hub.runs['conv-1'] = newestFirst([row('a', T0, 5 * MIN), row('b', T0 + 9 * 60 * MIN + 5 * MIN, 5 * MIN), row('c', T0 + 9 * 60 * MIN + 15 * MIN, 5 * MIN)])
    open()
    const turns = await screen.findAllByTestId('conversation-turn')
    const breaks = screen.getAllByTestId('conversation-break')
    expect(breaks).toHaveLength(1)
    expect(breaks[0]).toHaveAttribute('data-label', '9h 0m later')
    expect(Number(within(turns[0]!).getByTestId('conversation-turn-bar').getAttribute('data-width'))).toBeGreaterThan(0.1)
  })

  it('reads its totals from the Hub for the same conversation: 3 turns, 6 minutes, one unpriced, one failed', async () => {
    hub.runs['conv-1'] = newestFirst([
      row('a', T0, 1 * MIN, { cost_usd: 0.5 }),
      row('b', T0 + 20 * MIN, 2 * MIN, { cost_usd: null, cost_state: 'unpriced' }),
      row('c', T0 + 59 * MIN, 3 * MIN, { cost_usd: 0.25, run_status: 'failed', status: 'error', is_error: true }),
    ])
    open()
    const totals = await screen.findByTestId('conversation-totals')
    await waitFor(() => expect(totals).toHaveAttribute('data-model-calls', '6'))
    expect(totals).toHaveAttribute('data-turns', '3')
    expect(totals).toHaveAttribute('data-of', '3')
    expect(totals).toHaveAttribute('data-working-seconds', '360')
    expect(totals).toHaveAttribute('data-cost-usd-micros', '750000')
    expect(totals).toHaveAttribute('data-unpriced', '1')
    expect(totals).toHaveAttribute('data-failed', '1')
    expect(totals).toHaveTextContent('1 unpriced turn left out')
    expect(totals).toHaveTextContent('1 failed turn')
    expect(totals).toHaveTextContent('6m 0s')
    // The whole conversation is asked for with no bounds.
    const asked = paths().filter((u) => u.pathname.endsWith('/traces/totals'))
    expect(asked[0]!.searchParams.get('conversation_id')).toBe('conv-1')
    expect(asked[0]!.searchParams.has('since')).toBe(false)
  })

  it('unfolds a 10-minute turn to its spans on the turn’s own scale, and shows the selected call’s attributes', async () => {
    hub.runs['conv-1'] = [row('a', T0, 10 * MIN)]
    open()
    const turn = await screen.findByTestId('conversation-turn')
    fireEvent.click(within(turn).getByTestId('conversation-turn-toggle'))
    const spans = await within(turn).findAllByTestId('conversation-span')
    expect(spans).toHaveLength(1)
    expect(Number(spans[0]!.getAttribute('data-left'))).toBeCloseTo(0.5, 6)
    expect(within(turn).getByTestId('conversation-turn-scale-note')).toHaveTextContent('own')
    fireEvent.click(within(spans[0]!).getByRole('button', { name: /chat claude-haiku/ }))
    expect(within(screen.getByTestId('conversation-detail')).getAllByText(/claude-haiku-4-5/).length).toBeGreaterThan(0)
  })

  it('narrows 24 turns to 9–12, totals them as 4 of 24 with a since/until the Hub accepts, then says no turn matches', async () => {
    hub.runs['conv-1'] = turnsOf(24)
    open()
    await screen.findAllByTestId('conversation-turn')
    expect(screen.getAllByTestId('conversation-turn')).toHaveLength(24)
    fireEvent.change(screen.getByTestId('conversation-trace-from'), { target: { value: '9' } })
    fireEvent.change(screen.getByTestId('conversation-trace-to'), { target: { value: '12' } })
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(4))
    const totals = screen.getByTestId('conversation-totals')
    await waitFor(() => expect(totals).toHaveAttribute('data-model-calls', '8'))
    expect(totals).toHaveTextContent('4 of 24')
    expect(totals).toHaveAttribute('data-cost-usd-micros', '400000')
    const narrowed = paths().filter((u) => u.pathname.endsWith('/traces/totals') && u.searchParams.has('since')).slice(-1)[0]!
    expect(Date.parse(narrowed.searchParams.get('since')!)).toBe(T0 + 8 * 30 * MIN)
    expect(Date.parse(narrowed.searchParams.get('until')!)).toBe(T0 + 11 * 30 * MIN + 1000)

    // The last hour: every turn started days ago.
    fireEvent.change(screen.getByTestId('conversation-trace-from'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('conversation-trace-to'), { target: { value: '24' } })
    fireEvent.change(screen.getByTestId('conversation-trace-since'), { target: { value: '1h' } })
    expect(await screen.findByTestId('conversation-trace-empty')).toHaveTextContent('No turn')
    fireEvent.click(screen.getByTestId('conversation-trace-show-all'))
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(24))
    expect(screen.queryByTestId('conversation-trace-empty')).toBeNull()
  })

  it('pages the list past 200 runs', async () => {
    hub.runs['conv-1'] = turnsOf(205, 10 * MIN)
    open()
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(205))
    const lists = paths().filter((u) => /\/traces$/.test(u.pathname))
    expect(lists).toHaveLength(2)
    expect(lists[0]!.searchParams.get('limit')).toBe('200')
    expect(lists[1]!.searchParams.get('before')).toBeTruthy()
    expect(screen.getByTestId('conversation-totals')).toHaveAttribute('data-of', '205')
  })

  it('names the conversation it continued, opens that one’s 21 turns, and shows only its own 24', async () => {
    hub.runs['conv-1'] = turnsOf(24)
    hub.runs['conv-0'] = turnsOf(21).map((r) => ({ ...r, conversation_id: 'conv-0' }))
    hub.earlier['conv-1'] = { conversation_id: 'conv-0', title: 'Before the handoff' }
    open()
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(24))
    const link = await screen.findByTestId('conversation-trace-continued')
    expect(link).toHaveTextContent('Before the handoff')
    expect(link).toHaveAttribute('data-conversation-id', 'conv-0')
    fireEvent.click(link)
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(21))
    expect(screen.getByTestId('conversation-trace')).toHaveAttribute('data-conversation-id', 'conv-0')
    expect(screen.queryByTestId('conversation-trace-continued')).toBeNull()
  })

  it('requests no span on opening, one per unfolded turn, and says the cleared turn has no trace', async () => {
    hub.runs['conv-1'] = turnsOf(24)
    hub.cleared.add('r3')
    open()
    await waitFor(() => expect(screen.getAllByTestId('conversation-turn')).toHaveLength(24))
    expect(byRunRequests()).toHaveLength(0)
    const turns = screen.getAllByTestId('conversation-turn')
    fireEvent.click(within(turns[0]!).getByTestId('conversation-turn-toggle'))
    fireEvent.click(within(turns[2]!).getByTestId('conversation-turn-toggle'))
    await waitFor(() => expect(within(screen.getAllByTestId('conversation-turn')[2]!).getByTestId('conversation-turn-no-trace')).toBeInTheDocument())
    await within(screen.getAllByTestId('conversation-turn')[0]!).findAllByTestId('conversation-span')
    expect(byRunRequests().map((u) => u.pathname.split('/').pop()).sort()).toEqual(['r1', 'r3'])
    // Folding and unfolding again reads nothing more.
    fireEvent.click(within(screen.getAllByTestId('conversation-turn')[0]!).getByTestId('conversation-turn-toggle'))
    fireEvent.click(within(screen.getAllByTestId('conversation-turn')[0]!).getByTestId('conversation-turn-toggle'))
    expect(byRunRequests()).toHaveLength(2)
  })
})
