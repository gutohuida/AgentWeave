import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { useSSE, cancelReconnect, __resetSSEStateForTest } from '@/hooks/useSSE'
import { useDashboardRun, type DashboardRun, type PanelRun } from '@/api/dashboards'
import { DashboardsView } from '@/components/dashboards/DashboardsView'

// An agent's save reaches an open dashboard through the existing `dashboard_edited` event: the
// event refetches the run, and the view shows the edit as an edit (same bars, new widths; the
// removed panel leaving; the added one new).
const enc = new TextEncoder()
let push: (text: string) => void = () => {}
const frame = (type: string, data: object) => `event: ${type}\ndata: ${JSON.stringify({ project_id: 'p', ...data })}\n\n`

const panel = (p: Partial<PanelRun> & Pick<PanelRun, 'id' | 'title' | 'kind' | 'columns' | 'rows'>): PanelRun => ({
  query: 'select 1', row_count: p.rows.length, truncated: false, elapsed_ms: 1, error: null, warning: null, ...p,
})
const bar = (values: number[]) => panel({ id: 'b', title: 'Bars', kind: 'bar', columns: ['l', 'v'], rows: values.map((v, i) => [`l${i}`, v]) })
const old = panel({ id: 'o', title: 'Old', kind: 'number', columns: ['c'], rows: [[1]] })
const fresh = panel({ id: 'f', title: 'Fresh', kind: 'number', columns: ['c'], rows: [[2]] })
const runOf = (panels: PanelRun[]): DashboardRun => ({
  id: 'd1', name: 'D', description: '', author: 'A', updated_at: null, fetched_at: '2026-11-14T10:00:00Z', panels,
})
const summary = { id: 'd1', name: 'D', description: '', author: 'A', created_at: null, updated_at: null, panel_count: 2 }

describe('an agent saving an open dashboard', () => {
  let current: PanelRun[]
  let runCalls = 0
  beforeEach(() => {
    __resetSSEStateForTest()
    runCalls = 0
    current = [bar([1, 2, 3, 4]), old]
    useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'p', isConfigured: true, bootstrapState: 'ready' })
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes('/dashboards/d1/run')) {
        runCalls++
        return new Response(JSON.stringify(runOf(current)), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      const stream = new ReadableStream<Uint8Array>({
        start(c) {
          push = (t) => c.enqueue(enc.encode(t))
        },
      })
      return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    })
  })
  afterEach(() => {
    cancelReconnect()
    __resetSSEStateForTest()
  })

  it('dashboard_edited refetches the run: bars keep their elements, a panel is added and one leaves', async () => {
    function Probe() {
      useSSE()
      const run = useDashboardRun('d1')
      return (
        <DashboardsView dashboards={[summary]} selectedId="d1" run={run.data ?? null} refreshing={run.isFetching}
          onSelect={() => {}} onRefresh={() => {}} onDelete={() => {}} />
      )
    }
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Probe />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getAllByTestId('dashboard-panel')).toHaveLength(2))
    expect(runCalls).toBe(1)
    expect(document.querySelector('.is-new')).toBeNull()
    const before = [...document.querySelectorAll('svg.aw-dash-bar')] as SVGElement[]
    expect(before.map((b) => b.style.width)).toEqual(['25%', '50%', '75%', '100%'])

    current = [bar([4, 2, 3, 1]), fresh]
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
      push(frame('dashboard_edited', { dashboard_id: 'd1' }))
      await new Promise((r) => setTimeout(r, 150))
    })
    await waitFor(() => expect(runCalls).toBe(2))
    await waitFor(() => expect(screen.getByTestId('dashboard-panel-leaving').getAttribute('data-panel-id')).toBe('o'))
    expect(document.querySelector('[data-panel-id=f]')?.getAttribute('data-state')).toBe('new')
    const after = [...document.querySelectorAll('svg.aw-dash-bar')] as SVGElement[]
    after.forEach((el, i) => expect(el).toBe(before[i]))
    expect(after.map((b) => b.style.width)).toEqual(['100%', '50%', '75%', '25%'])
    await waitFor(() => expect(screen.queryByTestId('dashboard-panel-leaving')).toBeNull(), { timeout: 2000 })
  })
})
