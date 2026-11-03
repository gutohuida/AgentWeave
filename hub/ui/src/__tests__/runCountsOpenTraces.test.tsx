/**
 * A run count elsewhere opens Activity → Traces on exactly those runs
 * (a-traces-view-with-filters-grouping-and-stats, FR-12). Each count asks through
 * `openTraces`; the traces view takes the request in and sends it to the traces route as a filter.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import type { WorkTally } from '@/api/stats'
import type { TraceSummary } from '@/api/traces'
import { ActivityScreen } from '@/components/activity/ActivityScreen'
import { WorkView } from '@/components/activity/ProjectWork'
import { SpecBuildsSection } from '@/components/spec/page/SpecBuilds'
import type { BuildView } from '@/components/spec/page/model'
import { useConfigStore } from '@/store/configStore'
import { useTracesRequestStore } from '@/store/tracesRequestStore'
import payload from './fixtures/workTally.json'

vi.mock('@/api/logs', () => ({
  useLogs: () => ({ data: [], isLoading: false, error: null, hasOlder: false, loadOlder: vi.fn(), isLoadingOlder: false }),
}))
vi.mock('@/api/accounting', () => ({ useAccounting: () => ({ data: { recent_turns: [] } }) }))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [{ name: 'dev', color_index: 1 }] }) }))
vi.mock('@/components/activity/ProjectLedger', () => ({ ProjectLedger: () => <div data-testid="ledger-stub" /> }))
vi.mock('@/components/logs/LogsView', () => ({ LogsView: () => <div data-testid="logs-stub" /> }))

const TALLY = payload as unknown as WorkTally

function row(runId: string, task: string): TraceSummary {
  return {
    trace_id: `t-${runId}`,
    root_span_id: 's',
    run_id: runId,
    name: 'invoke_agent dev',
    operation: 'invoke_agent',
    kind: 'run',
    agent: 'dev',
    conversation_id: null,
    task_id: task,
    status: 'ok',
    status_message: null,
    start_time: '2026-11-02T10:00:00Z',
    end_time: '2026-11-02T10:01:00Z',
    ended: true,
    span_count: 3,
    model: 'haiku',
    task_ref: 'T-1',
    task_title: 'A task',
    cost_usd: 0.1,
    cost_state: 'measured',
    is_error: false,
  }
}

let urls: string[] = []

beforeEach(() => {
  urls = []
  useTracesRequestStore.getState().clear()
  window.history.replaceState(null, '', '/')
  useConfigStore.setState({ apiKey: 'k', hubUrl: 'http://hub.test', selectedProjectId: 'proj-a', isConfigured: true })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      urls.push(url)
      const body = { traces: [row('run-1', 'task-1'), row('run-2', 'task-1')], next_before: null }
      return {
        ok: true,
        status: 200,
        json: async () => body,
        text: async () => JSON.stringify(body),
        headers: new Headers({ 'content-type': 'application/json' }),
      }
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function withClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('a count asks for its runs', () => {
  it('a build’s row in the project work summary asks for that build’s runs', async () => {
    render(<WorkView tally={TALLY} grouping="spec" onGrouping={vi.fn()} since="" onSince={vi.fn()} />)
    await userEvent.click(within(screen.getByTestId('work-build-b-a1')).getByTestId('work-runs-open'))
    expect(useTracesRequestStore.getState().request).toMatchObject({ build: 'b-a1' })
    expect(window.location.search).toContain('tab=activity')
  })

  it('an agent’s row asks for that agent’s runs since the chosen day, and the total row for the project’s', async () => {
    render(<WorkView tally={TALLY} grouping="agent" onGrouping={vi.fn()} since="2026-10-01" onSince={vi.fn()} />)
    await userEvent.click(within(screen.getByTestId('work-row-agent-dev')).getByTestId('work-runs-open'))
    expect(useTracesRequestStore.getState().request).toMatchObject({ agent: 'dev', since: '2026-10-01T00:00:00Z' })
    await userEvent.click(within(screen.getByTestId('work-totals')).getByTestId('work-runs-open'))
    const request = useTracesRequestStore.getState().request!
    expect(request).toMatchObject({ since: '2026-10-01T00:00:00Z' })
    expect(request.agent).toBeUndefined()
  })

  it('a build card’s run count asks its section to open that build’s runs', async () => {
    const build = {
      id: 'build-7',
      number: 3,
      runs: 7,
      running: false,
      level: 'reviewed',
      driver: 'flow',
      builders: [],
      reviewers: [],
      lead: null,
      startedAt: '2026-11-01T10:00:00Z',
      finishedAt: '2026-11-01T11:00:00Z',
      landsOn: 'main',
      caught: [],
      openFixTasks: [],
      fixHeldReason: null,
      budget: null,
      tasks: {},
      time: { building: 0, reviewing: 0, checks: 0, held: 0, review: 0, waiting: 0 },
      cost: { build: null, review: null, lead: null, mend: null },
      unpriced: 0,
      checks: { runs: 0, passed: 0, failed: 0, seconds: 0 },
    } as unknown as BuildView
    const onOpenRuns = vi.fn()
    render(
      <SpecBuildsSection
        builds={[build]}
        canBuild
        changeOnly
        now={new Date('2026-11-02T00:00:00Z')}
        flash={null}
        onStartBuild={vi.fn()}
        onOpenRuns={onOpenRuns}
        onStop={vi.fn()}
        onCopyLink={vi.fn()}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: /7 runs/ }))
    expect(onOpenRuns).toHaveBeenCalledExactlyOnceWith(build)
  })
})

describe('Activity → Traces takes the request in', () => {
  it('lists the runs of a build through the route’s build filter, and lets go of it on request', async () => {
    useTracesRequestStore.getState().ask({ build: 'build-7', label: 'build 3' })
    withClient(<ActivityScreen onOpenTask={vi.fn()} />)
    expect(await screen.findByTestId('traces-view')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Traces' })).toHaveAttribute('aria-checked', 'true')
    await waitFor(() => expect(urls.some((u) => u.includes('build_id=build-7'))).toBe(true))
    expect(urls[0]).toContain('operation=invoke_agent')
    expect(screen.getByTestId('traces-request-note')).toHaveTextContent('build 3')
    expect(await screen.findAllByTestId('trace-row')).toHaveLength(2)
    // Taken in once: the store holds nothing for the next visit.
    expect(useTracesRequestStore.getState().request).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Show all runs' }))
    await waitFor(() => expect(urls[urls.length - 1]).not.toContain('build_id'))
  })

  it('lists the runs of a task through the route’s task filter', async () => {
    useTracesRequestStore.getState().ask({ task: 'task-1', label: 'task A task' })
    withClient(<ActivityScreen onOpenTask={vi.fn()} />)
    await waitFor(() => expect(urls.some((u) => u.includes('task_id=task-1'))).toBe(true))
    expect(urls.some((u) => u.includes('build_id'))).toBe(false)
  })

  it('is untouched when nothing asked: the Ledger leads', () => {
    withClient(<ActivityScreen onOpenTask={vi.fn()} />)
    expect(screen.getByTestId('ledger-stub')).toBeInTheDocument()
    expect(urls).toEqual([])
  })
})
