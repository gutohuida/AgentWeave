import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManagerIndicator } from '@/components/manager/ManagerIndicator'
import { SpecVaultWarnings } from '@/components/spec/SpecVaultWarnings'
import { SpecRetrospective } from '@/components/spec/page/SpecRetrospective'
import { VaultDistillationStatus } from '@/components/vault/VaultDistillationStatus'
import { useVaultMap } from '@/api/vault'
import { __resetSSEStateForTest, cancelReconnect } from '@/hooks/useSSE'
import { useConfigStore } from '@/store/configStore'
import { managerRunDestination, parseDestination, serializeDestination } from '@/lib/navigation'

/**
 * `background-manager-work-you-can-see` (BWYCS-3): the manager's icon on the item a run works on,
 * the top-bar indicator and its popover. The routes are stubbed at `fetch`, so the hooks are the
 * real ones, and the stream is a real `text/event-stream` body, so the events go through `useSSE`.
 *
 * Fixtures are in the order each route returns: `/runs/running` and `/runs/unseen-failures` oldest
 * first (`manager.running`, `manager.unseen_failures`), `/activity` newest first
 * (`manager.list_firings`).
 */

const PID = 'proj-a'
const SPEC_A = 'spec/changes/refunds/spec.json'
const SPEC_B = 'spec/changes/payouts/spec.json'

const ago = (seconds: number) => new Date(Date.now() - seconds * 1000).toISOString()

let running: unknown[] = []
let unseen: unknown[] = []
let firings: unknown[] = []
const hits: Record<string, number> = {}
const posted: Array<{ url: string; body: unknown }> = []
const enc = new TextEncoder()
let push: (type: string, data: object) => void = () => {}

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function count(name: string) {
  hits[name] = (hits[name] ?? 0) + 1
}

beforeEach(() => {
  __resetSSEStateForTest()
  running = []
  unseen = []
  firings = []
  posted.length = 0
  for (const key of Object.keys(hits)) delete hits[key]
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: PID, bootstrapState: 'ready' })
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (url.includes('/events')) {
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            push = (type, data) =>
              controller.enqueue(enc.encode(`event: ${type}\ndata: ${JSON.stringify({ project_id: PID, ...data })}\n\n`))
          },
        })
        return Promise.resolve(new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }))
      }
      if (method === 'POST') {
        posted.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
        if (url.endsWith('/runs/seen')) return Promise.resolve(new Response(null, { status: 204 }))
        return respond({ document: SPEC_A, queued: true }, 202)
      }
      if (url.endsWith('/manager/runs/running')) return count('running'), respond({ runs: running })
      if (url.endsWith('/manager/runs/unseen-failures')) return count('unseen'), respond({ failures: unseen })
      if (url.includes('/manager/activity')) return count('activity'), respond({ firings })
      if (url.endsWith('/manager/jobs'))
        return respond({
          jobs: [
            { key: 'spec-vault-check', title: 'Spec vault check' },
            { key: 'conversation-titles', title: 'Conversation titles' },
            { key: 'mender', title: 'Mender' },
          ],
        })
      if (url.endsWith('/project/documents'))
        return respond({ documents: [{ id: 'd1', path: SPEC_A, title: 'Refunds', kind: 'change-spec', phase: 'approved' }] })
      if (url.includes('/vault/warnings?')) return count('warnings'), respond({ warnings: [], checked: true })
      if (url.includes('/retrospectives?')) return count('retrospectives'), respond({ retrospectives: [] })
      if (url.endsWith('/vault/map')) return count('map'), respond({ entries: [] })
      return respond({ detail: 'Not Found' }, 404)
    }),
  )
})

afterEach(() => {
  cancelReconnect()
  __resetSSEStateForTest()
  vi.unstubAllGlobals()
})

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)
}

function run(id: string, job: string, subject: Record<string, unknown>, startedSecondsAgo = 5, extra: object = {}) {
  return { run_id: id, job, subject, trigger: 'requested', initiator: 'operator', started_at: ago(startedSecondsAgo), conversation_id: null, ...extra }
}

/** Wait for the stream to be open before pushing into it. */
async function streamOpen() {
  await waitFor(() => expect((fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.some(([u]) => String(u).includes('/events'))).toBe(true))
  await act(async () => {
    await new Promise((r) => setTimeout(r, 20))
  })
}

describe('top-bar-count (FR-7)', () => {
  it('shows a spinner and 3 for two title runs and a mender run in progress', async () => {
    running = [
      run('mrun-t1', 'conversation-titles', { conversation_id: 'conv-1' }, 30),
      run('mrun-t2', 'conversation-titles', { conversation_id: 'conv-2' }, 20),
      run('run-m1', 'mender', { stall: 'stall-1', reason: 'Task stuck' }, 10, { conversation_id: 'conv-m', trigger: 'stall' }),
    ]
    wrap(<ManagerIndicator onOpenRun={() => {}} onOpenConversation={() => {}} />)
    expect(await screen.findByTestId('manager-indicator-count')).toHaveTextContent('3')
    expect(screen.getByTestId('manager-indicator-busy')).toBeInTheDocument()
    expect(screen.getByTestId('manager-indicator')).toHaveAccessibleName('Manager: 3 runs in progress')
  })

  it('shows no count and no spinner with nothing in progress', async () => {
    wrap(<ManagerIndicator onOpenRun={() => {}} onOpenConversation={() => {}} />)
    await waitFor(() => expect(hits.running).toBeGreaterThan(0))
    expect(screen.queryByTestId('manager-indicator-count')).toBeNull()
    expect(screen.queryByTestId('manager-indicator-busy')).toBeNull()
  })

  it('counts a run the stream announces, and drops it when it ends, without a re-read deciding it', async () => {
    wrap(<ManagerIndicator onOpenRun={() => {}} onOpenConversation={() => {}} />)
    await streamOpen()
    running = [run('mrun-live', 'spec-vault-check', { document: SPEC_A })]
    await act(async () => push('manager_run_started', running[0] as object))
    expect(await screen.findByTestId('manager-indicator-count')).toHaveTextContent('1')
    running = []
    await act(async () => push('manager_run_ended', { ...(run('mrun-live', 'spec-vault-check', { document: SPEC_A }) as object), ended_at: ago(0), outcome: 'written', detail: null }))
    await waitFor(() => expect(screen.queryByTestId('manager-indicator-count')).toBeNull())
  })
})

describe('popover-rows-link (FR-8)', () => {
  beforeEach(() => {
    running = [
      run('mrun-run', 'spec-vault-check', { document: SPEC_A }, 20),
      run('run-mend', 'mender', { stall: 'stall-1', reason: 'Task stuck in review' }, 5, { conversation_id: 'conv-m', trigger: 'stall' }),
    ]
    // Newest first, as `/activity` lists firings.
    firings = [
      { id: 'evt-2', at: ago(60), job: 'spec-vault-check', trigger: 'requested', subject: { document: SPEC_A }, outcome: 'failed', detail: 'The model does not exist', duration_ms: 900, usage: null, run_id: 'mrun-bad', initiator: 'operator', started_at: ago(61) },
      { id: 'evt-1', at: ago(120), job: 'spec-vault-check', trigger: 'requested', subject: { document: SPEC_A }, outcome: 'written', detail: 'No conflicts kept', duration_ms: 4000, usage: { cost_usd_micros: 3000 }, run_id: 'mrun-fin', initiator: 'operator', started_at: ago(124) },
      { id: 'evt-0', at: ago(500), job: 'spec-vault-check', trigger: 'requested', subject: { document: SPEC_A }, outcome: 'written', detail: null, duration_ms: 1, usage: null },
    ]
  })

  it('lists the running, finished, failed and mender runs, each with job, subject and time', async () => {
    wrap(<ManagerIndicator onOpenRun={() => {}} onOpenConversation={() => {}} />)
    await screen.findByTestId('manager-indicator-count')
    fireEvent.mouseEnter(screen.getByTestId('manager-indicator').parentElement!)
    const popover = await screen.findByTestId('manager-popover')
    await waitFor(() => expect(within(popover).getByTestId('manager-popover-run-mrun-fin')).toBeInTheDocument())
    const runningRow = within(popover).getByTestId('manager-popover-run-mrun-run')
    expect(runningRow).toHaveTextContent('Spec vault check')
    expect(runningRow).toHaveTextContent('Refunds')
    expect(runningRow.textContent).toMatch(/Running 2\ds/)
    expect(within(popover).getByTestId('manager-popover-run-mrun-fin')).toHaveTextContent(/Finished/)
    expect(within(popover).getByTestId('manager-popover-run-mrun-bad')).toHaveTextContent(/Failed/)
    expect(within(popover).getByTestId('manager-popover-run-mrun-bad')).toHaveTextContent('The model does not exist')
    expect(within(popover).getByTestId('manager-popover-run-run-mend')).toHaveTextContent('Mender')
    expect(within(popover).getByTestId('manager-popover-run-run-mend')).toHaveTextContent('Task stuck in review')
    // A firing from before runs had ids is not a run.
    expect(popover.querySelectorAll('[data-testid^="manager-popover-run-"]:not([data-testid$="-conversation"])')).toHaveLength(4)
  })

  it('opens a finished row in Settings › Manager, and a mender row in its conversation too', async () => {
    const onOpenRun = vi.fn()
    const onOpenConversation = vi.fn()
    wrap(<ManagerIndicator onOpenRun={onOpenRun} onOpenConversation={onOpenConversation} />)
    await screen.findByTestId('manager-indicator-count')
    fireEvent.click(screen.getByTestId('manager-indicator'))
    fireEvent.click(await screen.findByTestId('manager-popover-run-mrun-fin'))
    expect(onOpenRun).toHaveBeenCalledWith('mrun-fin')
    fireEvent.click(screen.getByTestId('manager-indicator'))
    fireEvent.click(await screen.findByTestId('manager-popover-run-run-mend-conversation'))
    expect(onOpenConversation).toHaveBeenCalledWith('conv-m')
    fireEvent.click(screen.getByTestId('manager-popover-run-run-mend'))
    expect(onOpenRun).toHaveBeenCalledWith('run-mend')
  })

  it('a failed row opens that run too', async () => {
    const onOpenRun = vi.fn()
    wrap(<ManagerIndicator onOpenRun={onOpenRun} onOpenConversation={() => {}} />)
    fireEvent.click(await screen.findByTestId('manager-indicator'))
    fireEvent.click(await screen.findByTestId('manager-popover-run-mrun-bad'))
    expect(onOpenRun).toHaveBeenCalledWith('mrun-bad')
  })
})

describe('failure-cleared (b): hovering the top bar sees the failures it lists (FR-6)', () => {
  it('posts the listed unseen failures to /runs/seen', async () => {
    unseen = [
      { run_id: 'mrun-old', job: 'spec-vault-check', subject: { document: SPEC_B }, ended_at: ago(3600), detail: 'refused' },
      { run_id: 'mrun-new', job: 'spec-vault-check', subject: { document: SPEC_A }, ended_at: ago(60), detail: 'no such model' },
    ]
    wrap(<ManagerIndicator onOpenRun={() => {}} onOpenConversation={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('manager-indicator')).toHaveAttribute('data-failed', 'true'))
    fireEvent.mouseEnter(screen.getByTestId('manager-indicator').parentElement!)
    const popover = await screen.findByTestId('manager-popover')
    expect(within(popover).getByTestId('manager-popover-run-mrun-new')).toHaveTextContent('no such model')
    await waitFor(() => expect(posted.find((p) => p.url.endsWith('/runs/seen'))?.body).toEqual({ run_ids: ['mrun-old', 'mrun-new'] }))
  })
})

describe('icon-placements (FR-4)', () => {
  it("shows working on spec A's vault warnings and idle on spec B's while A is checked", async () => {
    running = [run('mrun-a', 'spec-vault-check', { document: SPEC_A, content_version: 'v3' })]
    wrap(
      <>
        <div data-testid="a"><SpecVaultWarnings path={SPEC_A} /></div>
        <div data-testid="b"><SpecVaultWarnings path={SPEC_B} /></div>
      </>,
    )
    await waitFor(() => expect(within(screen.getByTestId('a')).getByTestId('manager-icon')).toHaveAttribute('data-state', 'working'))
    expect(within(screen.getByTestId('a')).getByTestId('manager-icon')).toHaveAttribute('data-job', 'spec-vault-check')
    expect(within(screen.getByTestId('b')).getByTestId('manager-icon')).toHaveAttribute('data-state', 'idle')
    expect(screen.queryByText(/reload the list/)).toBeNull()
  })

  it("shows working on spec B's retrospective and idle on spec A's", async () => {
    running = [run('mrun-r', 'build-retrospective', { document: SPEC_B })]
    const props = { now: new Date(), flash: null, onCopyLink: () => {} }
    wrap(
      <>
        <div data-testid="a"><SpecRetrospective path={SPEC_A} {...props} /></div>
        <div data-testid="b"><SpecRetrospective path={SPEC_B} {...props} /></div>
      </>,
    )
    await waitFor(() => expect(within(screen.getByTestId('b')).getByTestId('manager-icon')).toHaveAttribute('data-state', 'working'))
    expect(within(screen.getByTestId('a')).getByTestId('manager-icon')).toHaveAttribute('data-state', 'idle')
  })

  it('shows working in the Vault header while any source is distilled', async () => {
    running = [run('mrun-d', 'vault-distillation', { source: 'src-1' }, 3, { trigger: 'source_added', initiator: 'autonomous' })]
    wrap(<VaultDistillationStatus />)
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'working'))
    expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-job', 'vault-distillation')
  })
})

describe('products-refresh (FR-5)', () => {
  const ended = (id: string, job: string, subject: object, outcome = 'written') => ({
    ...run(id, job, subject as Record<string, unknown>),
    ended_at: ago(0),
    duration_ms: 1000,
    outcome,
    detail: null,
    usage: null,
  })

  it("re-reads spec A's warnings when its check ends, and the icon goes idle", async () => {
    running = [run('mrun-a', 'spec-vault-check', { document: SPEC_A })]
    wrap(<SpecVaultWarnings path={SPEC_A} />)
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'working'))
    await streamOpen()
    const before = hits.warnings ?? 0
    running = []
    await act(async () => push('manager_run_ended', ended('mrun-a', 'spec-vault-check', { document: SPEC_A })))
    await waitFor(() => expect(hits.warnings).toBeGreaterThan(before))
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'idle'))
  })

  it("does not re-read spec A's warnings when spec B's check ends", async () => {
    wrap(<SpecVaultWarnings path={SPEC_A} />)
    await screen.findByTestId('manager-icon')
    await streamOpen()
    const before = hits.warnings ?? 0
    await act(async () => push('manager_run_ended', ended('mrun-b', 'spec-vault-check', { document: SPEC_B })))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(hits.warnings ?? 0).toBe(before)
  })

  it("re-reads a build's retrospectives when its retrospective ends", async () => {
    wrap(<SpecRetrospective path={SPEC_B} now={new Date()} flash={null} onCopyLink={() => {}} />)
    await screen.findByTestId('manager-icon')
    await streamOpen()
    const before = hits.retrospectives ?? 0
    await act(async () => push('manager_run_ended', ended('mrun-r', 'build-retrospective', { document: SPEC_B })))
    await waitFor(() => expect(hits.retrospectives).toBeGreaterThan(before))
  })

  it("re-reads the vault's map when a distillation ends", async () => {
    function MapReader() {
      useVaultMap()
      return null
    }
    wrap(
      <>
        <VaultDistillationStatus />
        <MapReader />
      </>,
    )
    await screen.findByTestId('manager-icon')
    await waitFor(() => expect(hits.map).toBe(1))
    await streamOpen()
    await act(async () => push('manager_run_ended', ended('mrun-d', 'vault-distillation', { source: 'src-1' })))
    await waitFor(() => expect(hits.map).toBe(2))
  })
})

describe('failure-persists and failure-cleared (a), (c) (FR-6)', () => {
  beforeEach(() => {
    unseen = [{ run_id: 'mrun-fail', job: 'spec-vault-check', subject: { document: SPEC_A }, ended_at: ago(86_400), detail: 'no such model' }]
  })

  it("shows spec A's unseen failure as failed, and opening its warnings marks it seen", async () => {
    wrap(<SpecVaultWarnings path={SPEC_A} />)
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'failed'))
    expect(screen.getByTestId('spec-vault-warnings-failure')).toHaveTextContent('no such model')
    await waitFor(() => expect(posted.find((p) => p.url.endsWith('/runs/seen'))?.body).toEqual({ run_ids: ['mrun-fail'] }))
    // Still failed in this view after the Hub stops listing it: it is what the operator arrived to.
    unseen = []
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'failed')
  })

  it("does not show spec A's failure on spec B, nor mark it seen there", async () => {
    wrap(<SpecVaultWarnings path={SPEC_B} />)
    await waitFor(() => expect(hits.unseen).toBeGreaterThan(0))
    expect(await screen.findByTestId('manager-icon')).toHaveAttribute('data-state', 'idle')
    expect(posted.filter((p) => p.url.endsWith('/runs/seen'))).toHaveLength(0)
  })

  it('goes straight from failed to working on Check now, with no idle between', async () => {
    wrap(<SpecVaultWarnings path={SPEC_A} />)
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'failed'))
    const states: Array<string | null> = []
    const observer = new MutationObserver(() => states.push(screen.queryByTestId('manager-icon')?.getAttribute('data-state') ?? null))
    observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['data-state'] })
    fireEvent.click(screen.getByTestId('spec-vault-warnings-check'))
    expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'working')
    await waitFor(() => expect(posted.some((p) => p.url.includes('/vault/warnings/check'))).toBe(true))
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })
    observer.disconnect()
    expect(states.filter((s) => s === 'idle')).toHaveLength(0)
  })

  it('gives the failure back when the Hub refuses Check now', async () => {
    wrap(<SpecVaultWarnings path={SPEC_A} />)
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'failed'))
    vi.mocked(fetch).mockImplementationOnce(() => respond({ detail: 'The job is off.' }, 409))
    fireEvent.click(screen.getByTestId('spec-vault-warnings-check'))
    expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'working')
    await waitFor(() => expect(screen.getByTestId('manager-icon')).toHaveAttribute('data-state', 'failed'))
    expect(await screen.findByText(/Could not start the check/)).toBeInTheDocument()
  })
})

describe("a run's detail address (Settings › Manager with run=<run_id>)", () => {
  it('writes and reads run=<run_id> on the manager section, for a job run and a mender run', () => {
    for (const id of ['mrun-0123456789ab', 'run-4f2a']) {
      const search = serializeDestination(managerRunDestination(PID, id))
      const params = new URLSearchParams(search)
      expect(params.get('tab')).toBe('environment')
      expect(params.get('section')).toBe('manager')
      expect(params.get('run')).toBe(id)
      expect(parseDestination(search)).toEqual(managerRunDestination(PID, id))
    }
  })

  it('drops a run id that is not one', () => {
    const parsed = parseDestination(`?project=${PID}&tab=environment&section=manager&run=${encodeURIComponent('<script>')}`)
    expect(parsed).toEqual({ kind: 'project', projectId: PID, tab: 'environment', environmentSection: 'manager' })
  })
})
