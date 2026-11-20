/**
 * A profile's runs and a flow's runs (profiles-threads-and-builds-everywhere FR-6, FR-13, D5).
 * The lists read GET /traces with `profile` or `loop_id`, keep the route's order (newest first),
 * say each run's kind, task, start and outcome, and open its trace with a link to its conversation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import type { Job } from '@/api/jobs'
import type { RunKind, TraceSummary } from '@/api/traces'
import { AgentRunsPage } from '@/components/agents/settings/AgentRunsPage'
import { FlowRuns } from '@/components/jobs/FlowRuns'
import { JobsView } from '@/components/jobs/JobsView'
import { useConfigStore } from '@/store/configStore'

function run(
  runId: string,
  kind: RunKind,
  minute: number,
  extra: Partial<TraceSummary> = {},
): TraceSummary {
  return {
    trace_id: `t-${runId}`,
    root_span_id: `s-${runId}`,
    run_id: runId,
    name: `invoke_agent alpha`,
    operation: 'invoke_agent',
    kind: 'run',
    agent: 'alpha',
    conversation_id: `conv-${runId}`,
    task_id: null,
    run_status: 'completed',
    status: 'ok',
    status_message: null,
    start_time: `2026-11-20T10:${String(minute).padStart(2, '0')}:00Z`,
    end_time: `2026-11-20T10:${String(minute).padStart(2, '0')}:30Z`,
    ended: true,
    span_count: 3,
    run_kind: kind,
    ...extra,
  }
}

/** The route's order: newest first. */
const PROFILE_RUNS: TraceSummary[] = [
  run('run-msg', 'message', 50),
  run('run-job', 'job', 40),
  run('run-mender', 'mender', 30, { run_status: 'failed', is_error: true }),
  run('run-review', 'review', 20, { task_id: 'task-2', task_ref: 'PR-2', task_title: 'Check it' }),
  run('run-task', 'task', 10, { task_id: 'task-1', task_ref: 'PR-1', task_title: 'Build it' }),
  run('run-thread', 'thread', 5),
  run('run-old', 'thread', 1, { agent: 'old-alpha' }),
]

const FLOW_RUNS: TraceSummary[] = [
  run('run-fr-b', 'task', 20, { agent: 'beta', task_ref: 'FR-T2', task_title: 'B', run_status: 'failed' }),
  run('run-fr-a', 'task', 10, { agent: 'alpha', task_ref: 'FR-T1', task_title: 'A' }),
]

let urls: string[] = []

function respond(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  }
}

beforeEach(() => {
  urls = []
  window.history.replaceState(null, '', '/')
  useConfigStore.setState({ apiKey: 'k', hubUrl: 'http://hub.test', selectedProjectId: 'proj-a', isConfigured: true })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      urls.push(url)
      if (url.includes('/traces/by-run/')) return respond({ detail: 'This run has no trace' }, 404)
      if (url.includes('loop_id=')) return respond({ traces: FLOW_RUNS, next_before: null })
      return respond({ traces: PROFILE_RUNS, next_before: null })
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

function rowIds(list: HTMLElement): string[] {
  return within(list)
    .getAllByRole('listitem')
    .map((li) => li.getAttribute('data-run-id') ?? '')
}

describe('profile-runs-listed', () => {
  it('lists all seven runs newest first with kind, task, start and outcome, the folded name included', async () => {
    withClient(<AgentRunsPage agent="alpha" />)
    const list = await screen.findByRole('list', { name: 'Runs of alpha' })
    expect(rowIds(list)).toEqual(PROFILE_RUNS.map((r) => r.run_id))
    expect(urls[0]).toContain('profile=alpha')
    expect(urls[0]).toContain('operation=invoke_agent')

    const rows = within(list).getAllByRole('listitem')
    const kinds = rows.map((li) => li.querySelector('.aw-run-kind')?.textContent)
    expect(kinds).toEqual(['Message', 'Job', 'Mender', 'Review', 'Task build', 'Thread', 'Thread'])
    expect(rows[4]).toHaveTextContent('PR-1 Build it')
    expect(rows[3]).toHaveTextContent('PR-2 Check it')
    expect(rows[2]).toHaveTextContent('Failed')
    expect(rows[6]).toHaveTextContent('Completed')
    for (const li of rows) expect(li.querySelector('time')?.getAttribute('dateTime')).toBeTruthy()
  })

  it('opens a run’s trace, and its conversation from there', async () => {
    const user = userEvent.setup()
    withClient(<AgentRunsPage agent="alpha" />)
    const list = await screen.findByRole('list', { name: 'Runs of alpha' })
    const folded = within(list).getAllByRole('listitem')[6]
    await user.click(within(folded).getByRole('button'))
    const detail = await screen.findByTestId('trace-detail')
    expect(detail).toHaveAttribute('data-run-id', 'run-old')
    await waitFor(() => expect(urls.some((u) => u.includes('/traces/by-run/run-old'))).toBe(true))
    await user.click(screen.getByRole('button', { name: /Open the conversation/ }))
    expect(window.location.search).toContain('conv-run-old')
    expect(window.location.search).toContain('old-alpha')
  })

  it('says a failed read with a way to try again, never that there are no runs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond({ detail: 'down' }, 500)))
    withClient(<AgentRunsPage agent="alpha" />)
    expect(await screen.findByTestId('run-list-error')).toHaveTextContent('could not be read')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByTestId('run-list-empty')).toBeNull()
  })
})

const ARCHIVED_FLOW: Job = {
  id: 'job-fr',
  project_id: 'proj-a',
  name: 'Night flow',
  agent: 'alpha',
  message: 'next',
  cron: '*/5 * * * *',
  session_mode: 'new',
  enabled: false,
  source: 'hub',
  created_at: '2026-11-19T10:00:00Z',
  run_count: 2,
  archived_at: '2026-11-20T11:00:00Z',
  loop: {
    id: 'loop-fr',
    label: 'Night flow',
    purpose: '',
    stop_when_queue_empties: false,
    stop_reason: 'operator stopped it',
    stopped_at: '2026-11-20T10:59:00Z',
    archived_at: '2026-11-20T11:00:00Z',
    queue: {},
    open_questions: 0,
    firing_active: false,
  },
}

describe('flow-runs-listed', () => {
  it('lists a stopped, archived flow’s two runs newest first with profile, task, start and outcome', async () => {
    const user = userEvent.setup()
    withClient(
      <JobsView
        jobs={[]}
        archived={[ARCHIVED_FLOW]}
        onToggle={() => {}}
        onRunNow={() => {}}
        onArchive={() => {}}
        onNew={() => {}}
        colorIndexOf={() => undefined}
        renderArchivedRuns={(job) => <FlowRuns job={job} />}
        now={new Date('2026-11-20T12:00:00Z')}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Show archived/ }))
    await user.click(screen.getByRole('button', { name: 'Show the runs of Night flow' }))
    const list = await screen.findByRole('list', { name: 'Runs of Night flow' })
    expect(urls[0]).toContain('loop_id=loop-fr')
    expect(rowIds(list)).toEqual(['run-fr-b', 'run-fr-a'])
    const [first, second] = within(list).getAllByRole('listitem')
    expect(first.querySelector('.aw-run-profile')).toHaveTextContent('beta')
    expect(first).toHaveTextContent('FR-T2 B')
    expect(first).toHaveTextContent('Failed')
    expect(second.querySelector('.aw-run-profile')).toHaveTextContent('alpha')
    expect(second).toHaveTextContent('Completed')

    await user.click(within(first).getByRole('button'))
    expect(await screen.findByTestId('trace-detail')).toHaveAttribute('data-run-id', 'run-fr-b')
    await user.click(screen.getByRole('button', { name: /Open the conversation/ }))
    expect(window.location.search).toContain('conv-run-fr-b')
  })
})
