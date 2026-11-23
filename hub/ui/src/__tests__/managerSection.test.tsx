import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ManagerSection } from '@/components/settings/sections/ManagerSection'
import { chooseMenuOption, menuSelect, openMenuSelect } from './support/menuSelect'
import { useConfigStore } from '@/store/configStore'
import { toast } from '@/lib/toast'
import managerJobsRoute from './fixtures/managerJobs.route.json'

vi.mock('@/lib/toast', () => ({ toast: vi.fn() }))

/** `the-hubs-background-jobs-are-configured-on-a-manager-page`, task manager-section. The routes are
 *  stubbed at `fetch`, so the hooks, their 404 handling and the PATCH bodies are the real ones. */

const RUNNERS = [
  { id: 'runner-haiku', name: 'Haiku 4.5', cli: 'claude', model: null, model_unrecognised: false },
  { id: 'runner-titles', name: 'Titler', cli: 'claude', model: 'claude-opus-5', model_unrecognised: false },
]
const CATALOG = {
  providers: [{
    provider: 'claude',
    label: 'Claude',
    controls: [],
    models: [
      { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5', aliases: ['haiku'], context_window: 200_000, default: false },
      { id: 'claude-opus-5', label: 'Opus 5', aliases: ['opus'], context_window: 1_000_000, default: true },
    ],
  }],
}
const JOB = {
  key: 'conversation-titles',
  title: 'Thread titles',
  description: 'Names a conversation after its first exchange.',
  trigger: 'turn_completed',
  needs_runner: false,
  enabled: true,
  runner_id: 'runner-titles',
  model: 'claude-haiku-4-5-20251001',
  // The route returns `mode` for every job, not only the chapters one.
  mode: 'automatic',
}
// Newest first, the order the run log lists them in once each is a run (`asRun`).
const FIRINGS = [
  {
    id: 'evt-2', at: '2026-10-09T15:02:00+00:00', job: 'conversation-titles', trigger: 'turn_completed',
    subject: { conversation_id: 'conv-2' }, runner_id: 'runner-titles', cli: 'claude',
    model: 'claude-haiku-4-5-20251001', outcome: 'empty', detail: null, duration_ms: 900, usage: null,
  },
  {
    id: 'evt-1', at: '2026-10-09T15:01:00+00:00', job: 'conversation-titles', trigger: 'turn_completed',
    subject: { conversation_id: 'conv-1' }, runner_id: 'runner-titles', cli: 'claude',
    model: 'claude-haiku-4-5-20251001', outcome: 'written', detail: 'Bakery naming ideas',
    duration_ms: 4200, usage: null,
  },
]

interface Firing {
  id: string; at: string; job: string; trigger: string; subject: Record<string, string | undefined>; runner_id: string; cli: string
  model: string | null; outcome: string; detail: string | null; duration_ms: number; usage?: Record<string, number> | null
  answer?: string; run_id?: string; initiator?: string
}

/** A firing fixture as the run log lists it: `GET /manager/runs`, newest first. */
function asRun(f: Firing) {
  return {
    run_id: f.run_id ?? `mrun-${f.id}`, job: f.job, subject: f.subject, trigger: f.trigger,
    initiator: f.initiator ?? 'autonomous', started_at: f.at, ended_at: f.at, duration_ms: f.duration_ms,
    outcome: f.outcome, detail: f.detail, usage: f.usage ?? null,
    no_cost_reason: f.usage ? null : 'never reached a model', conversation_id: null, answer: f.answer ?? null,
  }
}

function totalsOf(runs: ReturnType<typeof asRun>[]) {
  const totals: Record<string, { runs: number; failed: number; cost_usd_micros: number | null }> = {}
  for (const run of runs) {
    const total = (totals[run.job] ??= { runs: 0, failed: 0, cost_usd_micros: null })
    total.runs += 1
    if (run.outcome === 'failed') total.failed += 1
    const cost = run.usage?.cost_usd_micros
    if (cost != null) total.cost_usd_micros = (total.cost_usd_micros ?? 0) + cost
  }
  return totals
}

/** The log route's answer for these firings, and a run's own route's for one of them. */
function runLog(firings: Firing[], url = '') {
  const runs = firings.map(asRun)
  const one = /\/manager\/runs\/([^?/]+)/.exec(url)
  if (one) {
    const found = runs.find((r) => r.run_id === decodeURIComponent(one[1]))
    return found ? { status: 200, body: found } : { status: 404, body: { detail: 'No run' } }
  }
  return { status: 200, body: { runs, totals: totalsOf(runs), has_more: false } }
}

type Route = (url: string, init?: RequestInit) => { status: number; body: unknown } | undefined
let manager: Route
const patches: Array<{ url: string; body: unknown }> = []

function respond(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  patches.length = 0
  useConfigStore.setState({
    apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a',
  })
  manager = () => undefined
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') patches.push({ url, body: JSON.parse(String(init.body)) })
    const routed = manager(url, init)
    if (routed) return respond(routed.status, routed.body)
    if (url.endsWith('/runners')) return respond(200, RUNNERS)
    if (url.endsWith('/model-catalog')) return respond(200, CATALOG)
    return respond(404, { detail: 'Not Found' })
  }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Project settings → Manager', () => {
  it('says this Hub has no manager yet when the routes answer 404', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText(/This Hub has no manager yet/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(errors).not.toHaveBeenCalled()
    errors.mockRestore()
  })

  it('lists each job with its switch, runner and model, and the runs newest first', async () => {
    const user = userEvent.setup()
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog(FIRINGS, url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    await screen.findByTestId('manager-job-conversation-titles')
    expect(screen.getByRole('heading', { name: 'Thread titles' })).toBeInTheDocument()
    expect(screen.getByTestId('manager-job-conversation-titles-enabled')).toHaveAttribute('aria-checked', 'true')
    await waitFor(() => expect(menuSelect('Thread titles runner')).toHaveTextContent('Titler'))
    // Each runner named by its own model (F268), as every runner menu is.
    const options = await openMenuSelect(user, 'Thread titles runner')
    expect(options.find((o) => o.textContent?.startsWith('Titler'))).toHaveTextContent('Opus 5 · claude')
    await user.keyboard('{Escape}')
    expect(menuSelect('Thread titles model')).toHaveTextContent('Haiku 4.5')

    const first = await screen.findByTestId('manager-run-mrun-evt-2')
    expect(within(first).getByText('Nothing to do')).toBeInTheDocument()
    const second = screen.getByTestId('manager-run-mrun-evt-1')
    expect(within(second).getByText('Written')).toBeInTheDocument()
  })

  it('names a firing’s conversation by its title when the Hub knows it', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog(FIRINGS, url)
      if (url.includes('/conversations')) {
        return { status: 200, body: { conversations: [{ id: 'conv-1', agent: 'a', title: 'Bakery naming ideas', lifecycle: 'open', updated_at: '2026-10-09T15:01:00+00:00' }] } }
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByTestId('manager-run-mrun-evt-1-subject')).toHaveTextContent('Bakery naming ideas')
    expect(screen.getByTestId('manager-run-mrun-evt-2-subject')).toHaveTextContent('thread conv-2')
  })

  it('badges an answered report and opens what the model answered (F641, F581)', async () => {
    const answered = {
      ...FIRINGS[1], id: 'evt-3', job: 'vault-reports', trigger: 'report_filed', subject: { report: 'r-1' },
      outcome: 'answered', detail: 'answered: the entry stands',
      answer: '{"outcome": "answered", "answer": "The source says 437 euros."}',
    }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog([answered], url)
      return undefined
    }
    render(<ManagerSection run="mrun-evt-3" />, { wrapper })
    const row = await screen.findByTestId('manager-run-mrun-evt-3')
    expect(within(row).getByText('Answered')).toBeInTheDocument()
    // The row does not carry the answer, which runs long; the run's detail does.
    expect(within(row).queryByText(/The source says 437 euros/)).toBeNull()
    const detail = await screen.findByTestId('manager-run-detail')
    expect(within(detail).getByText(/The source says 437 euros/)).toBeInTheDocument()
    expect(within(detail).getByText('answered: the entry stands')).toBeInTheDocument()
  })

  it('says what each run worked on, a vault source by its name (F719)', async () => {
    const distilled = (id: string, source: string) => ({
      ...FIRINGS[1], id, job: 'vault-distillation', trigger: 'source_uploaded',
      subject: { source }, outcome: 'written', detail: '1 fact stored, 0 dropped',
    })
    const firings = [
      distilled('evt-5', 'src-aaa'),
      distilled('evt-4', 'src-bbb'),
      { ...FIRINGS[1], id: 'evt-3', job: 'spec-vault-check', subject: { document: 'spec/changes/x' } },
      { ...FIRINGS[1], id: 'evt-2', job: 'vault-reports', subject: { report: 'rpt-1', entry: 'src-aaa' } },
    ]
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog(firings, url)
      if (url.endsWith('/vault/map')) {
        return {
          status: 200,
          body: { entries: [{ id: 'src-aaa', name: 'On-call handbook' }, { id: 'src-bbb', name: 'Refunds' }] },
        }
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText('source "On-call handbook" (src-aaa)')).toBeInTheDocument()
    expect(screen.getByTestId('manager-run-mrun-evt-4-subject')).toHaveTextContent('source "Refunds" (src-bbb)')
    expect(screen.getByTestId('manager-run-mrun-evt-3-subject')).toHaveTextContent('document spec/changes/x')
    expect(screen.getByTestId('manager-run-mrun-evt-2-subject')).toHaveTextContent(
      'report rpt-1 on "On-call handbook" (src-aaa)',
    )
  })

  it('words the empty runner choice by what the job does with none (F590)', async () => {
    const user = userEvent.setup()
    const vault = {
      ...JOB, key: 'vault-distillation', title: 'Vault distillation', needs_runner: true,
      runner_id: null, model: null,
    }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, vault] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    await screen.findByTestId('manager-job-conversation-titles')
    const titles = (await openMenuSelect(user, 'Thread titles runner')).map((o) => o.textContent)
    expect(titles[0]).toMatch(/^The profile’s own runner/)
    await user.keyboard('{Escape}')
    const distilChoices = (await openMenuSelect(user, 'Vault distillation runner')).map((o) => o.textContent)
    expect(distilChoices[0]).toMatch(/^No runner/)
    expect(distilChoices.some((t) => /profile’s own runner/.test(t ?? ''))).toBe(false)
    await user.keyboard('{Escape}')
    const distil = screen.getByTestId('manager-job-vault-distillation')
    expect(within(distil).getByText(/does nothing until a runner is chosen/i)).toBeInTheDocument()
    expect(within(distil).getByText(/On, but it has no runner, so it will not run/)).toBeInTheDocument()
  })

  it('names the model the mender runs on when none is chosen, and no other job’s', async () => {
    const mender = {
      ...JOB, key: 'mender', title: 'Mender', needs_runner: true, model: null,
      default_model: { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5' },
    }
    const titles = { ...JOB, model: null }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [titles, mender] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    await screen.findByTestId('manager-job-mender')
    await waitFor(() => expect(menuSelect('Mender model')).toHaveTextContent('Sonnet 5.5 (the mender’s default)'))
    expect(menuSelect('Mender model')).not.toHaveTextContent('The runner’s model')
    expect(menuSelect('Thread titles model')).toHaveTextContent('The runner’s model')
  })

  it('says the mender uses its default model, not the runner’s, when its model is cleared', async () => {
    const user = userEvent.setup()
    const mender = {
      ...JOB, key: 'mender', title: 'Mender', needs_runner: true, model: 'claude-opus-5-5',
      default_model: { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5' },
    }
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') return { status: 200, body: { ...mender, model: null } }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [mender] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    await waitFor(() => expect(menuSelect('Mender model')).not.toBeDisabled())

    await chooseMenuOption(user, 'Mender model', /Sonnet 5.5 \(the mender’s default\)/)

    await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: 'Mender uses Sonnet 5.5', tone: 'success' }))
  })

  it('sends only what changed when a control is used', async () => {
    const user = userEvent.setup()
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') {
        return { status: 200, body: { ...JOB, enabled: false } }
      }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })

    fireEvent.click(await screen.findByTestId('manager-job-conversation-titles-enabled'))
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].url).toBe('http://hub/api/v1/projects/proj-a/manager/jobs/conversation-titles')
    expect(patches[0].body).toEqual({ enabled: false })

    await waitFor(() => expect(menuSelect('Thread titles model')).not.toBeDisabled())
    await chooseMenuOption(user, 'Thread titles model', /The runner’s model/)
    await waitFor(() => expect(patches).toHaveLength(2))
    expect(patches[1].body).toEqual({ model: null })
  })

  it('clears a model chosen for another CLI when the runner changes', async () => {
    const user = userEvent.setup()
    const runners = [...RUNNERS, { id: 'runner-codex', name: 'Codex', cli: 'codex', model: null, model_unrecognised: false }]
    manager = (url, init) => {
      if (url.includes('/manager/jobs') && init?.method === 'PATCH') return { status: 200, body: JOB }
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      if (url.endsWith('/runners')) return { status: 200, body: runners }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    await waitFor(() => expect(menuSelect('Thread titles runner')).toHaveTextContent('Titler'))
    await chooseMenuOption(user, 'Thread titles runner', /^Codex/)
    await waitFor(() => expect(patches).toHaveLength(1))
    expect(patches[0].body).toEqual({ runner_id: 'runner-codex', model: null })
  })

  it('withholds the job controls when the runners cannot be read, rather than misstate the runner', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      if (url.endsWith('/runners')) return { status: 500, body: { detail: 'boom' } }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Thread titles runner' })).toBeNull()
  })

  it('says when no job has run yet', async () => {
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [{ ...JOB, enabled: false }] } }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    expect(await screen.findByText(/No job has run yet/)).toBeInTheDocument()
  })

  it('shows the chapters job’s firing choice, each run’s tokens and money, and the project total', async () => {
    const user = userEvent.setup()
    const chapters = {
      key: 'chapters', title: 'Thread chapters', description: 'Writes the Thread’s chapters.', trigger: 'document_approved',
      needs_runner: true, enabled: true, runner_id: 'runner-haiku', model: null, mode: 'button',
      firing_choice: { button: 'Weave the thread', where: 'the Thread page', automatic: 'after a document is approved' },
      usage_total: { firings: 2, input_tokens: 1300, output_tokens: 500, cost_usd_micros: 95_000 },
    }
    const firing = (id: string, usage: Record<string, number>) => ({
      id, at: '2026-10-09T15:01:00+00:00', job: 'chapters', trigger: 'requested', subject: {}, runner_id: 'runner-haiku',
      cli: 'claude', model: null, outcome: 'written', detail: null, duration_ms: 4200, usage,
    })
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, chapters] } }
      if (url.includes('/manager/runs')) {
        return runLog([
          firing('evt-b', { input_tokens: 800, output_tokens: 200, cost_usd_micros: 60_000 }),
          firing('evt-a', { input_tokens: 500, output_tokens: 300, cost_usd_micros: 35_000 }),
        ], url)
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    await waitFor(() => expect(menuSelect('Thread chapters firing')).toHaveTextContent('Button only'))
    expect(screen.getByTestId('manager-job-chapters-total')).toHaveTextContent('2 firings · 1,800 tokens · $0.10')
    expect(await screen.findByTestId('manager-run-mrun-evt-b-cost')).toHaveTextContent('1,000 tokens · $0.06')
    expect(screen.getByTestId('manager-run-mrun-evt-a-cost')).toHaveTextContent('800 tokens · $0.04')
    expect(screen.queryByTestId('manager-job-conversation-titles-total')).toBeNull()
    expect(screen.queryByText('Thread titles firing')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Thread titles firing' })).toBeNull()

    await chooseMenuOption(user, 'Thread chapters firing', /^Automatic/)
    await waitFor(() => expect(patches).toContainEqual({ url: expect.stringContaining('/manager/jobs/chapters'), body: { mode: 'automatic' } }))
  })

  // The fixture is what `GET /manager/jobs` answers for a new project;
  // `hub/tests/test_manager_jobs.py` fails when the route stops answering it.
  it('offers the firing choice on exactly the jobs the listing says have a button', async () => {
    const user = userEvent.setup()
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: managerJobsRoute }
      if (url.includes('/manager/runs')) return runLog([], url)
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    await waitFor(() => expect(menuSelect('Build retrospective firing')).toHaveTextContent('Automatic'))
    expect(menuSelect('Thread chapters firing')).toHaveTextContent('Automatic')
    expect(menuSelect('Pre-mortem firing')).toHaveTextContent('Automatic')
    for (const { key, title, firing_choice } of managerJobsRoute.jobs) {
      if (key !== 'build-retrospective' && key !== 'chapters' && key !== 'pre-mortem') {
        expect(firing_choice).toBeNull()
        expect(screen.queryByRole('button', { name: `${title} firing` })).toBeNull()
      }
    }
    expect(within(screen.getByTestId('manager-job-build-retrospective')).getByText(/Button only: just when you press Review this build on a spec document's page/)).toBeInTheDocument()

    await openMenuSelect(user, 'Build retrospective firing')
    expect(screen.getByRole('menuitemradio', { name: /Only when you press Review this build/ })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await chooseMenuOption(user, 'Build retrospective firing', /^Button only/)
    await waitFor(() => expect(patches).toContainEqual({ url: 'http://hub/api/v1/projects/proj-a/manager/jobs/build-retrospective', body: { mode: 'button' } }))
  })

  it('counts cache tokens in a run and in the total, and breaks them down in a tooltip', async () => {
    const usage = { input_tokens: 10, output_tokens: 4486, cache_read_tokens: 0, cache_write_tokens: 7679, cost_usd_micros: 37798 }
    const chapters = {
      key: 'chapters', title: 'Thread chapters', description: 'Writes the Thread’s chapters.', trigger: 'document_approved',
      needs_runner: true, enabled: true, runner_id: 'runner-haiku', model: null, mode: 'button',
      usage_total: { firings: 1, ...usage },
    }
    manager = (url) => {
      if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, chapters] } }
      if (url.includes('/manager/runs')) {
        return runLog([{
          id: 'evt-a', at: '2026-10-09T15:01:00+00:00', job: 'chapters', trigger: 'requested', subject: {}, runner_id: 'runner-haiku',
          cli: 'claude', model: null, outcome: 'written', detail: null, duration_ms: 4200, usage,
        }], url)
      }
      return undefined
    }
    render(<ManagerSection />, { wrapper })
    const total = await screen.findByTestId('manager-job-chapters-total')
    expect(total).toHaveTextContent('1 firing · 12,175 tokens · $0.04')
    expect(total).toHaveAttribute('title', '10 input · 4,486 output · 0 cache read · 7,679 cache write')
    expect(await screen.findByTestId('manager-run-mrun-evt-a-cost')).toHaveTextContent('12,175 tokens · $0.04')
  })

  // log-columns, log-by-job, mender-in-log (BWYCS-4): fixtures in the order `GET /manager/runs` returns.
  describe('the run log', () => {
    const run = (id: string, over: Record<string, unknown>) => ({
      run_id: id, job: 'conversation-titles', subject: {}, trigger: 'turn_completed', initiator: 'autonomous',
      started_at: '2026-10-09T15:00:00+00:00', ended_at: '2026-10-09T15:00:05+00:00', duration_ms: 5000,
      outcome: 'written', detail: null, usage: null, no_cost_reason: 'the runner reported no cost',
      conversation_id: null, ...over,
    })
    const CHECK = { key: 'spec-vault-check', title: 'Spec vault check', description: 'Checks a spec.', trigger: 'spec_saved', needs_runner: true, enabled: true, runner_id: 'runner-haiku', model: null, mode: 'automatic' }
    const MENDER = { key: 'mender', title: 'Mender', description: 'Mends stalls.', trigger: 'stall_recorded', needs_runner: false, enabled: true, runner_id: null, model: null, mode: 'automatic' }

    it('shows each run’s job, subject, trigger, manual or automatic, start, duration, outcome, failure reason and cost or why none', async () => {
      const runs = [
        run('mrun-never', { job: 'chapters', trigger: 'requested', initiator: 'operator', outcome: 'failed', detail: 'Did nothing: the Chapters job is on but has no runner.', duration_ms: 0, no_cost_reason: 'never reached a model' }),
        run('mrun-distil', { job: 'vault-distillation', subject: { source: 'src-1' }, trigger: 'source_uploaded', usage: { input_tokens: 800, output_tokens: 200, cost_usd_micros: 60_000 }, no_cost_reason: null, duration_ms: 65_000 }),
        run('mrun-now', { job: 'spec-vault-check', subject: { document: 'spec/changes/x' }, trigger: 'check_now', initiator: 'operator', outcome: 'failed', detail: 'The check was refused.', duration_ms: 12_000 }),
      ]
      manager = (url) => {
        if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, CHECK] } }
        if (url.includes('/manager/runs')) return { status: 200, body: { runs, totals: {}, has_more: false } }
        return undefined
      }
      render(<ManagerSection />, { wrapper })
      const now = await screen.findByTestId('manager-run-mrun-now')
      expect(now).toHaveTextContent('Spec vault check')
      expect(screen.getByTestId('manager-run-mrun-now-subject')).toHaveTextContent('document spec/changes/x')
      expect(screen.getByTestId('manager-run-mrun-now-trigger')).toHaveTextContent('Check now · Manual')
      expect(within(now).getByText('Failed')).toBeInTheDocument()
      // The reason is on the row, not behind a disclosure.
      expect(screen.getByTestId('manager-run-mrun-now-reason')).toHaveTextContent('The check was refused.')
      expect(screen.getByTestId('manager-run-mrun-now-cost')).toHaveTextContent('the runner reported no cost')

      expect(screen.getByTestId('manager-run-mrun-distil-trigger')).toHaveTextContent('Source uploaded · Automatic')
      expect(screen.getByTestId('manager-run-mrun-distil-cost')).toHaveTextContent('1,000 tokens · $0.06')
      expect(screen.queryByTestId('manager-run-mrun-distil-reason')).toBeNull()

      expect(screen.getByTestId('manager-run-mrun-never-reason')).toHaveTextContent('has no runner')
      expect(screen.getByTestId('manager-run-mrun-never-cost')).toHaveTextContent('never reached a model')
      // Each row's link names its run.
      expect(screen.getByRole('button', { name: 'Open run mrun-never' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Open run mrun-now' })).toBeInTheDocument()
    })

    it('narrows to one job and shows its totals beside the others’', async () => {
      const user = userEvent.setup()
      const asked: string[] = []
      const checks = [
        run('mrun-c2', { job: 'spec-vault-check', usage: { cost_usd_micros: 100_000 }, no_cost_reason: null }),
        run('mrun-c1', { job: 'spec-vault-check', outcome: 'failed', detail: 'refused', usage: { cost_usd_micros: 50_000 }, no_cost_reason: null }),
        run('mrun-c0', { job: 'spec-vault-check', usage: { cost_usd_micros: 25_000 }, no_cost_reason: null }),
      ]
      const titles = Array.from({ length: 60 }, (_, n) => run(`mrun-t${n}`, {}))
      const totals = {
        'conversation-titles': { runs: 60, failed: 0, cost_usd_micros: null },
        'spec-vault-check': { runs: 3, failed: 1, cost_usd_micros: 175_000 },
      }
      manager = (url) => {
        if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, CHECK] } }
        if (url.includes('/manager/runs')) {
          asked.push(url)
          const narrowed = url.includes('job=spec-vault-check')
          return { status: 200, body: { runs: narrowed ? checks : titles.slice(0, 50), totals, has_more: !narrowed } }
        }
        return undefined
      }
      render(<ManagerSection />, { wrapper })
      await screen.findByTestId('manager-run-mrun-t0')
      expect(screen.queryByTestId('manager-run-mrun-c0')).toBeNull()
      expect(screen.getByTestId('manager-job-spec-vault-check-totals')).toHaveTextContent('3 runs · 1 failed · $0.17')
      expect(screen.getByTestId('manager-job-conversation-titles-totals')).toHaveTextContent('60 runs · 0 failed · no cost recorded')

      await chooseMenuOption(user, 'Filter the run log by job', /^Spec vault check/)
      expect(await screen.findByTestId('manager-run-mrun-c0')).toBeInTheDocument()
      await waitFor(() => expect(screen.queryByTestId('manager-run-mrun-t0')).toBeNull())
      expect(asked.some((url) => url.includes('job=spec-vault-check'))).toBe(true)
      expect(screen.getByTestId('manager-job-spec-vault-check-totals')).toHaveTextContent('3 runs · 1 failed')
    })

    it('lists a mender run with its stall’s reason and cost, and links to its thread', async () => {
      const user = userEvent.setup()
      const opened: string[] = []
      const runs = [run('run-mending', {
        job: 'mender', trigger: 'stall_recorded', subject: { stall: 'stall-1', reason: 'The merge of task-x failed.' },
        outcome: 'answered', duration_ms: 90_000, usage: { cost_usd_micros: 100_000 }, no_cost_reason: null, conversation_id: 'conv-mending',
      })]
      manager = (url) => {
        if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB, MENDER] } }
        if (url.includes('/manager/runs')) return { status: 200, body: { runs, totals: {}, has_more: false } }
        return undefined
      }
      render(<ManagerSection onOpenConversation={(id) => opened.push(id)} />, { wrapper })
      const row = await screen.findByTestId('manager-run-run-mending')
      expect(row).toHaveTextContent('Mender')
      expect(screen.getByTestId('manager-run-run-mending-subject')).toHaveTextContent('The merge of task-x failed.')
      expect(screen.getByTestId('manager-run-run-mending-cost')).toHaveTextContent('$0.10')
      await user.click(screen.getByTestId('manager-run-run-mending-conversation'))
      expect(opened).toEqual(['conv-mending'])
    })

    it('closes a run’s detail, and says so when the run is unknown', async () => {
      const user = userEvent.setup()
      const opened: Array<string | null> = []
      manager = (url) => {
        if (url.includes('/manager/jobs')) return { status: 200, body: { jobs: [JOB] } }
        if (url.includes('/manager/runs')) return runLog([], url)
        return undefined
      }
      render(<ManagerSection run="mrun-nope" onOpenRun={(id) => opened.push(id)} />, { wrapper })
      expect(await screen.findByRole('alert')).toHaveTextContent('mrun-nope')
      await user.click(screen.getByTestId('manager-run-detail-close'))
      expect(opened).toEqual([null])
    })
  })
})
