import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecRetrospective } from '@/components/spec/page/SpecRetrospective'
import type { BuildRetrospective } from '@/api/manager'
import { useConfigStore } from '@/store/configStore'
import routeAnswer from './fixtures/buildRetrospectives.route.json'

/**
 * The retrospective on a spec page (`a-finished-spec-gets-a-build-retrospective`, FR-3, FR-7, FR-9).
 * The fixture is `GET .../jobs/build-retrospective/retrospectives` as a real drive saved it
 * (drive8020/20261101-203658). The route answers newest first (`list_for_document`; pinned by
 * `test_the_list_is_newest_first_with_what_the_page_shows`), and every list here is in that order.
 * The hooks and the page are real; only `fetch` is stubbed.
 */

// The trace drawer itself is covered by traces.test.tsx; here a trace link is a button that reports
// which run it was asked to open.
const traceOpened = vi.hoisted(() => vi.fn())
vi.mock('@/components/traces/TraceDrawer', () => ({
  TraceButton: ({ runId, testId }: { runId?: string; testId?: string }) => (
    <button type="button" data-testid={testId} onClick={() => traceOpened(runId)}>
      trace
    </button>
  ),
  TraceDrawerPanel: () => null,
}))

const real = routeAnswer[0] as unknown as BuildRetrospective
const PATH = 'spec/changes/hello-file/spec.json'
const failed: BuildRetrospective = {
  id: 'evt-failed',
  at: '2026-11-01T22:00:00+00:00',
  trigger: 'requested',
  model: 'claude-haiku-5-5',
  outcome: 'failed',
  detail: 'The model did not answer within 600 seconds.',
  duration_ms: 0,
  usage: null,
  cost_usd_micros: null,
  parts: 1,
  vault_source: null,
  report: null,
}
const older: BuildRetrospective = {
  ...real,
  id: 'evt-older',
  at: '2026-10-30T09:15:00+00:00',
  model: 'claude-sonnet-5-5',
  report: {
    ...real.report!,
    what_worked: [{ text: 'The older report said this.', cites: ['run-1'] }],
  },
}

let answers: { retrospectives: BuildRetrospective[] }
let presses: Array<{ status: number; body: unknown }>
let pressed: number

function respond(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <SpecRetrospective path={PATH} now={new Date('2026-11-01T23:00:00Z')} flash={null} onCopyLink={() => undefined} />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  pressed = 0
  presses = []
  answers = { retrospectives: [] }
  useConfigStore.setState({ isConfigured: true, selectedProjectId: 'proj-1', hubUrl: 'http://hub', apiKey: 'k' })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options: RequestInit = {}) => {
      if (options.method === 'POST') {
        expect(url).toContain(`/manager/jobs/build-retrospective/run?path=${encodeURIComponent(PATH)}`)
        pressed += 1
        const next = presses.shift() ?? { status: 202, body: { started: true } }
        return respond(next.status, next.body)
      }
      expect(url).toContain(`/manager/jobs/build-retrospective/retrospectives?path=${encodeURIComponent(PATH)}`)
      return respond(200, answers)
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the spec page shows the newest and the failures (FR-9)', () => {
  beforeEach(() => {
    answers = { retrospectives: [failed, real, older] }
  })

  it('shows the failure with its reason and a run-again action', async () => {
    show()
    const failure = await screen.findByTestId('retro-failed')
    expect(failure).toHaveTextContent('The last retrospective failed')
    expect(failure).toHaveTextContent('The model did not answer within 600 seconds.')
    await userEvent.click(within(failure).getByRole('button', { name: 'Run it again' }))
    await waitFor(() => expect(pressed).toBe(1))
  })

  it('shows the newer written one with its time, trigger, model, parts and cost', async () => {
    show()
    const newest = await screen.findByTestId('retro-newest')
    const facts = within(newest).getByTestId('retro-facts')
    expect(facts).toHaveTextContent(/Made\s*Nov 1, \d\d:39/)
    expect(facts).toHaveTextContent('The last task was approved')
    expect(facts).toHaveTextContent('claude-haiku-5-5')
    expect(facts).toHaveTextContent(/Parts\s*1/)
    expect(facts).toHaveTextContent('<$0.01')
    expect(facts).toHaveTextContent(/Claims dropped\s*4/)
  })

  it('keeps the older one reachable, closed until it is opened', async () => {
    show()
    const earlier = await screen.findByTestId('retro-earlier')
    expect(screen.queryByText('The older report said this.')).toBeNull()
    await userEvent.click(within(earlier).getByRole('button', { name: /Oct 30.*Written/ }))
    expect(within(earlier).getByText('The older report said this.')).toBeInTheDocument()
    expect(within(earlier).getByText('claude-sonnet-5-5')).toBeInTheDocument()
  })

  it('takes the first row of the route as the newest', async () => {
    answers = { retrospectives: [real, older] }
    show()
    const newest = await screen.findByTestId('retro-newest')
    expect(newest).toHaveTextContent('claude-haiku-5-5')
    expect(screen.queryByTestId('retro-failed')).toBeNull()
  })
})

describe('every section of the report is there (FR-7)', () => {
  const titles = ['Where the time went', 'Send-backs', 'What the spec missed', 'Staffing', 'Cost', 'Friction', 'What worked', 'What to improve', 'Lessons', 'Transcripts read']

  it('names the real send-back, its transcript and the empty section, as a real report stored them', async () => {
    answers = { retrospectives: [real] }
    show()
    const newest = await screen.findByTestId('retro-newest')
    for (const title of titles) expect(within(newest).getByRole('heading', { name: title })).toBeInTheDocument()
    expect(within(newest).getByTestId('retro-send-back')).toHaveTextContent('HF-1')
    expect(within(newest).getByText('Nothing shows the spec missed anything.')).toBeInTheDocument()
    expect(newest.querySelector('[data-section="transcripts_read"]')).toHaveTextContent(real.report!.transcripts_read[0]!.run_id)
  })

  it('says there was nothing in each empty section', async () => {
    const nothing = {
      where_time_went: 'Nothing was recorded about where the time went.',
      send_backs: 'Nothing was sent back.',
      spec_missed: 'Nothing shows the spec missed anything.',
      staffing: 'Nothing to say about staffing.',
      cost: 'No cost was recorded.',
      friction: 'No friction was recorded.',
      what_worked: 'Nothing was called out as working.',
      improvements: 'Nothing to improve was grounded in the records.',
      lessons: 'No lessons were grounded in the records.',
      transcripts_read: 'No run was flagged, so no transcript was read.',
    }
    answers = { retrospectives: [{ ...real, report: { ...real.report!, nothing } }] }
    show()
    const newest = await screen.findByTestId('retro-newest')
    for (const title of titles) expect(within(newest).getByRole('heading', { name: title })).toBeInTheDocument()
    for (const said of Object.values(nothing)) expect(within(newest).getByText(said)).toBeInTheDocument()
  })

  it('words each of the three causes and four labels', async () => {
    const row = real.report!.send_backs[0]!
    const send_backs = ['defect', 'process', 'spec'].map((cause, i) => ({ ...row, transition_id: `ttr-${i}`, cause }))
    const improvements = ['code_and_checks', 'specs', 'staffing_and_running', 'tooling'].map((label) => ({ label, text: label, cites: ['run-1'] }))
    answers = { retrospectives: [{ ...real, report: { ...real.report!, send_backs, improvements } }] }
    show()
    await screen.findByTestId('retro-newest')
    expect(screen.getAllByTestId('retro-send-back').map((n) => n.querySelector('.aw-sp-retro-tag')?.textContent)).toEqual(['Defect in the work', 'Tooling or process', 'The spec was wrong'])
    expect(screen.getAllByTestId('retro-improvement').map((n) => n.querySelector('.aw-sp-retro-tag')?.textContent)).toEqual([
      "The project's code and checks",
      'How its specs are written',
      'How its builds are staffed and run',
      'The tooling itself',
    ])
  })
})

describe('Review this build (FR-3)', () => {
  const button = () => screen.getByRole('button', { name: 'Review this build' })

  it('says one is running after the first press, and the Hub\'s sentence after the second', async () => {
    presses = [
      { status: 202, body: { started: true } },
      { status: 409, body: { detail: 'A retrospective of this document is in progress.' } },
    ]
    show()
    await screen.findByText('No retrospective yet.')
    await userEvent.click(button())
    expect(await screen.findByTestId('retro-running')).toBeInTheDocument()
    await userEvent.click(button())
    expect(await screen.findByTestId('retro-refusal')).toHaveTextContent('A retrospective of this document is in progress.')
    expect(pressed).toBe(2)
  })

  it('says why when the job has no runner', async () => {
    presses = [{ status: 409, body: { detail: 'The build retrospective job has no runner.' } }]
    show()
    await screen.findByText('No retrospective yet.')
    await userEvent.click(button())
    expect(await screen.findByTestId('retro-refusal')).toHaveTextContent('has no runner')
    expect(screen.queryByTestId('retro-running')).toBeNull()
  })

  it('stops saying so once the firing appears in the list', async () => {
    presses = [
      { status: 202, body: { started: true } },
      { status: 409, body: { detail: 'A retrospective of this document is in progress.' } },
    ]
    const { client } = show()
    await screen.findByText('No retrospective yet.')
    await userEvent.click(button())
    await screen.findByTestId('retro-running')
    await userEvent.click(button())
    await screen.findByTestId('retro-refusal')
    answers = { retrospectives: [real] }
    await client.invalidateQueries()
    await screen.findByTestId('retro-newest')
    await waitFor(() => expect(screen.queryByTestId('retro-running')).toBeNull())
    expect(screen.queryByTestId('retro-refusal')).toBeNull()
  })

  it('draws nothing on a Hub that predates the job', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(404, { detail: 'Not Found' })))
    const { container } = show()
    await waitFor(() => expect(container.querySelector('section')).toBeNull())
  })
})

describe('a transcript read opens its run’s trace', () => {
  it('opens each listed run’s own trace', async () => {
    answers = { retrospectives: [real] }
    show()
    const newest = await screen.findByTestId('retro-newest')
    traceOpened.mockClear()
    const runs = real.report!.transcripts_read.map((r) => r.run_id)
    for (const run of runs) await userEvent.click(within(newest).getByTestId(`retro-transcript-trace-${run}`))
    expect(traceOpened.mock.calls).toEqual(runs.map((run) => [run]))
  })
})
