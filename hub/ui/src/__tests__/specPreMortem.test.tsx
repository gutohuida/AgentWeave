import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPreMortem } from '@/components/spec/page/SpecPreMortem'
import type { PreMortem } from '@/api/manager'
import { useConfigStore } from '@/store/configStore'
import managerJobsRoute from './fixtures/managerJobs.route.json'

/**
 * The Pre-mortem section on a spec page, fed from the Hub
 * (`the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions`, FR-11). The route
 * answers newest first (`pre_mortem.list_for_document`; pinned by
 * `test_a_button_whose_reader_finds_nothing_or_fails_is_listed_unwritten`), and the list here is in
 * that order. The jobs listing is the route's own fixture. Only `fetch` is stubbed.
 */

const PATH = 'spec/changes/hello-file/spec.json'
const failed: PreMortem = {
  id: 'evt-failed',
  at: '2026-11-22T22:00:00+00:00',
  trigger: 'requested',
  model: 'claude-haiku-5-5',
  outcome: 'failed',
  detail: 'the CLI is not installed',
  cost_usd_micros: null,
  findings: [],
}
const written: PreMortem = {
  id: 'evt-written',
  at: '2026-11-22T21:00:00+00:00',
  trigger: 'criteria_written',
  model: 'claude-haiku-5-5',
  outcome: 'written',
  detail: 'Found 1 ways the change could fail.',
  cost_usd_micros: 900,
  findings: [{ story: 'Under load the route took 900ms.', requirement: 'FR-1', cites: ['app.py:12'] }],
}

let preMortems: PreMortem[]
let enabled: boolean
let posted: unknown[]

function respond(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPreMortem path={PATH} now={new Date('2026-11-22T23:00:00Z')} flash={null} onCopyLink={() => undefined} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  preMortems = []
  enabled = true
  posted = []
  useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1', hubUrl: 'http://hub', apiKey: 'k' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options: RequestInit = {}) => {
      if (options.method === 'POST') {
        expect(url).toContain('/manager/jobs/pre-mortem/run')
        posted.push(JSON.parse(String(options.body)))
        return respond(202, { started: true })
      }
      if (url.includes('/manager/jobs/pre-mortem/pre-mortems')) {
        expect(url).toContain(`?path=${encodeURIComponent(PATH)}`)
        return respond(200, { pre_mortems: preMortems })
      }
      if (url.includes('/manager/jobs')) {
        const jobs = managerJobsRoute.jobs.map((job) => (job.key === 'pre-mortem' ? { ...job, enabled } : job))
        return respond(200, { jobs })
      }
      return respond(404, { detail: 'not here' })
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the Pre-mortem section on a spec page (FR-11)', () => {
  it('shows the written findings and the last failure, and the button posts the path', async () => {
    preMortems = [failed, written]
    show()
    const newest = await screen.findByTestId('premortem-newest')
    expect(within(newest).getByTestId('premortem-finding')).toHaveTextContent('Under load the route took 900ms.')
    expect(within(newest).getByTestId('premortem-finding')).toHaveTextContent('FR-1')
    expect(newest).toHaveTextContent('The acceptance criteria were written')
    expect(screen.getByTestId('premortem-failed')).toHaveTextContent('the CLI is not installed')

    await userEvent.click(await screen.findByRole('button', { name: 'Run a pre-mortem' }))
    await waitFor(() => expect(posted).toEqual([{ path: PATH }]))
  })

  it('withholds the button and says where to switch it on while the job is off', async () => {
    enabled = false
    show()
    expect(await screen.findByTestId('premortem-off')).toHaveTextContent('The Pre-mortem job is off in this project.')
    expect(screen.queryByRole('button', { name: 'Run a pre-mortem' })).toBeNull()
  })
})
