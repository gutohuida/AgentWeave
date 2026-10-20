/**
 * The trace view (a-run-is-a-trace-you-can-export). The model is driven with a page in the order
 * the route returns it — spans by start time — including a span whose parent is on another page;
 * the drawer is driven through `fetch`, so the 404-means-no-trace contract is exercised at the
 * seam the hook actually reads.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import type { Span, TraceDetail } from '@/api/traces'
import { useConfigStore } from '@/store/configStore'
import { TraceButton } from '@/components/traces/TraceDrawer'
import { buildWaterfall, traceExtent } from '@/components/traces/traceModel'
import { parseHeaderLines } from '@/components/environment/traceHeaders'
import { TracesSection } from '@/components/environment/TracesSection'

function span(partial: Partial<Span> & Pick<Span, 'span_id' | 'start_time'>): Span {
  return {
    trace_id: 't1',
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

const root = span({
  span_id: 'root',
  name: 'invoke_agent builder',
  operation: 'invoke_agent',
  status: 'error',
  status_message: 'run failed',
  start_time: '2026-10-19T10:00:00.000Z',
  end_time: '2026-10-19T10:00:10.000Z',
  attributes: { 'gen_ai.agent.name': 'builder' },
})
const chat = span({
  span_id: 'chat1',
  parent_span_id: 'root',
  name: 'chat claude-haiku',
  start_time: '2026-10-19T10:00:01.000Z',
  end_time: '2026-10-19T10:00:04.000Z',
  attributes: {
    'gen_ai.request.model': 'claude-haiku',
    'gen_ai.output.messages': [{ role: 'assistant', parts: [{ type: 'text', content: 'Hello there' }] }],
  },
})
const tool = span({
  span_id: 'tool1',
  parent_span_id: 'chat1',
  name: 'execute_tool Bash',
  operation: 'execute_tool',
  status: 'error',
  status_message: 'exit 1',
  start_time: '2026-10-19T10:00:02.000Z',
  end_time: '2026-10-19T10:00:03.000Z',
  attributes: { 'gen_ai.tool.name': 'Bash' },
})
const orphan = span({
  span_id: 'orphan',
  parent_span_id: 'not-on-this-page',
  name: 'aw.judge',
  operation: 'aw.judge',
  start_time: '2026-10-19T10:00:05.000Z',
  end_time: '2026-10-19T10:00:05.500Z',
  attributes: { 'aw.decision.allowed': true },
})
const open = span({
  span_id: 'wait',
  parent_span_id: 'root',
  name: 'aw.permission_wait',
  operation: 'aw.permission_wait',
  start_time: '2026-10-19T10:00:06.000Z',
  end_time: null,
  ended: false,
})

// Route order: by start time, root first.
const detail: TraceDetail = {
  trace_id: 't1',
  kind: 'run',
  run_id: 'run-1',
  root,
  spans: [root, chat, tool, orphan, open],
  total: 5,
  offset: 0,
  limit: 500,
}

describe('buildWaterfall', () => {
  it('nests by parent, hangs an off-page parent on the root, and draws an open span to the root end', () => {
    const rows = buildWaterfall(root, detail.spans, Date.parse('2026-10-19T10:00:30Z'))
    expect(rows.map((row) => [row.span.span_id, row.depth])).toEqual([
      ['root', 0],
      ['chat1', 1],
      ['tool1', 2],
      ['orphan', 1],
      ['wait', 1],
    ])
    const wait = rows.find((row) => row.span.span_id === 'wait')!
    expect(wait.open).toBe(true)
    expect(wait.durationMs).toBe(4000)
    expect(rows[2].offsetMs).toBe(2000)
  })

  it('draws a still-running trace to now', () => {
    const live = { ...root, end_time: null, ended: false }
    const now = Date.parse('2026-10-19T10:00:20Z')
    expect(traceExtent(live, [live, chat], now).totalMs).toBe(20000)
  })

  it('works on a later page whose spans do not include the root', () => {
    const rows = buildWaterfall(root, [tool], Date.parse('2026-10-19T10:00:30Z'))
    expect(rows.map((row) => [row.span.span_id, row.depth])).toEqual([
      ['root', 0],
      ['tool1', 1],
    ])
  })
})

describe('parseHeaderLines', () => {
  it('reads Name=value and Name: value lines, and refuses a line without a value', () => {
    expect(parseHeaderLines('Authorization=Bearer a=b\n\nx-team: core')).toEqual({
      headers: { Authorization: 'Bearer a=b', 'x-team': 'core' },
    })
    expect(parseHeaderLines('justaname')).toHaveProperty('error')
  })
})

const fetchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('TraceButton', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    useConfigStore.setState({
      apiKey: 'aw_live_test',
      hubUrl: 'http://hub.test',
      isConfigured: true,
      selectedProjectId: 'proj-a',
    })
  })
  afterEach(() => {
    cleanup()
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it('reads a 404 for a run as "no trace", not an error', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, text: async () => '{"detail":"no trace"}' })
    render(<TraceButton runId="run-old" testId="open" />, { wrapper })
    fireEvent.click(screen.getByTestId('open'))
    expect(await screen.findByText('No trace')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://hub.test/api/v1/projects/proj-a/traces/by-run/run-old?offset=0&limit=500',
    )
  })

  it('draws the run, marks the error span, and opens a span with its content folded', async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => detail })
    render(<TraceButton runId="run-1" testId="open" />, { wrapper })
    fireEvent.click(screen.getByTestId('open'))
    await screen.findByTestId('trace-waterfall')

    expect(screen.getByTestId('trace-row-tool1')).toHaveAttribute('data-status', 'error')
    // The root is selected first.
    expect(screen.getByTestId('trace-span-detail')).toHaveTextContent('invoke_agent builder')

    fireEvent.click(screen.getByTestId('trace-row-chat1'))
    await waitFor(() =>
      expect(screen.getByTestId('trace-span-detail')).toHaveTextContent('chat claude-haiku'),
    )
    const toggle = screen.getByRole('button', { name: /gen_ai\.output\.messages/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Hello there')).toBeNull()
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Hello there')).toBeInTheDocument()
  })

  it('offers paging when the trace has more spans than one page', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...detail, total: 1200 }),
    })
    render(<TraceButton runId="run-1" testId="open" />, { wrapper })
    fireEvent.click(screen.getByTestId('open'))
    const paging = await screen.findByTestId('trace-paging')
    expect(paging).toHaveTextContent('1–5 of 1,200')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes('offset=500'))).toBe(true),
    )
  })
})

describe('TracesSection recent traces', () => {
  const settings = {
    otlp_endpoint: null,
    otlp_header_names: [],
    export_enabled: false,
    enabled_at: null,
    last_export_at: null,
    last_error: null,
    exported_spans: 0,
    span_count: 3,
    trace_count: 2,
    oldest_trace_at: null,
    record_reads: false,
    spans_by_operation: { invoke_agent: 1, 'aw.request': 2 },
    dropped_spans: 0,
  }
  const summary = (partial: Record<string, unknown>) => ({
    root_span_id: 's',
    run_id: null,
    agent: null,
    conversation_id: null,
    task_id: null,
    status: 'unset',
    status_message: null,
    start_time: '2026-10-20T01:00:00+00:00',
    end_time: '2026-10-20T01:00:01+00:00',
    ended: true,
    span_count: 1,
    ...partial,
  })

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    useConfigStore.setState({
      apiKey: 'aw_live_test',
      hubUrl: 'http://hub.test',
      isConfigured: true,
      selectedProjectId: 'proj-a',
    })
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/traces/settings')) return { ok: true, status: 200, json: async () => settings }
      const operation = new URL(url).searchParams.get('operation')
      const traces =
        operation === 'aw.request'
          ? [summary({ trace_id: 'tr', name: 'POST /api/v1/projects/{project_id}/tasks', operation, kind: 'request' })]
          : [summary({ trace_id: 'tw', name: 'invoke_agent builder', operation: 'invoke_agent', kind: 'run', run_id: 'run-1', agent: 'builder' })]
      return { ok: true, status: 200, json: async () => ({ traces, next_before: null }) }
    })
  })
  afterEach(() => {
    cleanup()
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it("lists runs by default and the Hub's own requests, labelled, when asked", async () => {
    render(<TracesSection />, { wrapper })
    expect(await screen.findByText('builder')).toBeInTheDocument()
    const listed = () => fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => /\/traces\?/.test(url))
    expect(listed()[0]).toContain('operation=invoke_agent')
    expect(screen.getByTestId('trace-kind-invoke_agent')).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByTestId('trace-kind-aw.request'))
    expect(await screen.findByText(/POST \/api\/v1\/projects/)).toBeInTheDocument()
    expect(screen.getByText('· request')).toBeInTheDocument()
    expect(listed().slice(-1)[0]).toContain('operation=aw.request')

    fireEvent.click(screen.getByTestId('trace-kind-all'))
    await waitFor(() => expect(listed().slice(-1)[0]).not.toContain('operation='))
  })
})
