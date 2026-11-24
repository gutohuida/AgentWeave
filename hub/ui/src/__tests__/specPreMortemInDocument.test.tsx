import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'
import { SpecPage } from '@/components/spec/SpecPage'
import { SpecPanelContainer } from '@/components/spec/page/SpecPanelContainer'
import type { PreMortem } from '@/api/manager'
import type { SpecPossibleFact } from '@/api/vault'
import managerJobsRoute from './fixtures/managerJobs.route.json'

/* Spec `the-spec-process-uses-what-the-hub-already-knows`, task `spec-ui`: the pre-mortem at the end
 * of the Document part on the side panel and the full spec page (FR-7, criterion document-tab-end),
 * and a requirement's possible backing facts on the full page only (FR-10, the UI half of
 * possible-not-final). The Hub is a stubbed `fetch` answering each route in the order it returns:
 * the pre-mortems newest first with each firing's findings in the order they were written
 * (`pre_mortem.list_for_document`), and `GET /vault/warnings` with its possible facts beside the
 * warnings, in document order (`vault_spec_check.document_possible_facts`). */

vi.mock('@/hooks/useSSE', () => ({
  useSSEConnectionState: () => 'open',
  useSSE: () => {},
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

const PATH = 'spec/changes/demo/spec.json'
const DOC_ID = 'spdoc-demo'

const payload = {
  title: 'Demo change',
  kind: 'change-spec',
  summary: 'A demo summary.',
  problem: 'A demo problem.',
  design: 'Short.',
  scope: { in_scope: ['One thing'], non_goals: ['Another thing'] },
  requirements: [1, 2, 3, 4].map((n) => ({ key: `r${n}`, modal: 'MUST', statement: `Requirement number ${n} holds.`, rationale: null })),
  acceptance_criteria: [1, 2, 3, 4].map((n) => ({ key: `c${n}`, requirement: `r${n}`, given: `given ${n}`, when: `when ${n}`, then: `then ${n}` })),
  tasks: [{ key: 'plan', title: 'Plan it', description: 'd', depends_on: [], requirements: ['r1'] }],
  open_questions: [],
}
const html = `<html><body><script type="application/agentweave-spec+json" id="aw-spec-payload">${JSON.stringify(payload)}</script></body></html>`

const answered = { note: 'Each list now says why it is empty.', by: 'Architect', at: '2026-11-23T21:39:00+00:00' }
const WRITTEN: PreMortem = {
  id: 'evt-written',
  at: '2026-11-23T21:04:16+00:00',
  trigger: 'criteria_written',
  model: 'claude-sonnet-5-5',
  outcome: 'written',
  detail: 'Found 4 ways the change could fail.',
  cost_usd_micros: 101_933,
  // As the route numbers them: the first written is finding 1.
  findings: [
    { requirement: 'FR-2', story: 'The lists ship mostly empty.', cites: ['vault_spec_check.py:118'], answer: answered },
    { requirement: 'FR-3', story: 'The uses route scans every firing per request.', cites: [], answer: null },
    { requirement: 'FR-1', story: 'Counts drift between the views.', cites: [], answer: null },
    { requirement: null, story: 'A fact with no line citation opens nowhere.', cites: [], answer: null },
  ],
}

const POSSIBLE: SpecPossibleFact = {
  requirement: 'FR-2',
  fact: 'fct-disputed',
  claim: 'Gaps warn and never gate: the operator can always approve anyway.',
  source: 'spec-flow-rules.md',
}

interface Hub {
  preMortems: PreMortem[]
  jobOn: boolean
  running: unknown[]
  possible: SpecPossibleFact[]
}
let hub: Hub

const coverage = (identifier: string) => ({
  identifier,
  requirement_id: `req-${identifier}`,
  document_id: DOC_ID,
  state: 'not_started',
  integration: 'not_applicable',
  evidence_count: 0,
  accepted_count: 0,
  linked_task_ids: [],
  reason: null,
})

function route(url: string): unknown {
  const u = new URL(url, 'http://hub.test')
  const p = u.pathname.replace('/api/v1/projects/proj-test', '')
  if (p === '/project/specs')
    return {
      specs: [{ path: PATH, title: 'Demo change', kind: 'change-spec', state: 'filed', parent: null, order: 0, document_id: DOC_ID, phase: 'exploring' }],
      home: PATH,
      manifest: { state: 'valid', version: 1 },
      missing: [],
      diagnostics: [],
    }
  if (p === '/project/documents')
    return {
      documents: [
        { id: DOC_ID, path: PATH, title: 'Demo change', kind: 'change-spec', phase: 'exploring', rigor: 'contract', content_digest: null, explore_closed: false, updated_at: '2026-11-23T09:00:00Z' },
      ],
    }
  if (p === '/project/spec' && u.searchParams.get('path') === PATH)
    return { path: PATH, content: html, updated_at: '2026-11-23T09:00:00Z', content_version: 'v1', builds: [] }
  if (p === '/project/spec/coverage')
    return { requirements: ['FR-1', 'FR-2', 'FR-3', 'FR-4'].map(coverage), diagnostics: [], totals: {}, integration: {}, unserved: [] }
  if (p === '/tasks') return { tasks: [], total: 0, has_more: false }
  if (p === '/agents') return [{ name: 'Builder', status: 'idle', message_count: 0, active_task_count: 0 }]
  if (p === '/manager/jobs')
    return { jobs: managerJobsRoute.jobs.map((job) => (job.key === 'pre-mortem' ? { ...job, enabled: hub.jobOn } : job)) }
  if (p === '/manager/jobs/pre-mortem/pre-mortems') {
    expect(u.searchParams.get('path')).toBe(PATH)
    return { pre_mortems: hub.preMortems }
  }
  if (p === '/manager/runs/running') return { runs: hub.running }
  if (p === '/manager/runs/unseen-failures') return { failures: [] }
  if (p === '/vault/warnings') {
    expect(u.searchParams.get('path')).toBe(PATH)
    // A possible fact is answered beside the warnings, never among them: no warning names it.
    return { warnings: [], checked: true, possible_facts: hub.possible }
  }
  return undefined
}

function installHub() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = route(url)
      if (body === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
}

let queryClient: QueryClient
function renderPage() {
  return render(
    <QueryClientProvider client={queryClient}>
      <SpecPage document={PATH} onOpenDocument={vi.fn()} />
    </QueryClientProvider>,
  )
}
function renderPanel() {
  return render(
    <QueryClientProvider client={queryClient}>
      <SpecPanelContainer path={PATH} onOpenDocument={vi.fn()} />
    </QueryClientProvider>,
  )
}

const section = (id: string) => document.getElementById(`section-${id}`)
const sections = () => Array.from(document.querySelectorAll('section.aw-sp-section')).map((s) => s.id)

beforeEach(() => {
  cleanup()
  localStorage.clear()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useConfigStore.setState({ apiKey: 'aw_live_TESTKEY', hubUrl: 'http://hub.test', selectedProjectId: 'proj-test', isConfigured: true, bootstrapState: 'ready', mode: 'light' })
  hub = { preMortems: [WRITTEN], jobOn: true, running: [], possible: [] }
  installHub()
})
afterEach(() => vi.unstubAllGlobals())

/** The pre-mortem shows its count, each finding with its requirement and story, and the answered
 *  one's note, author and time. */
async function expectFindings() {
  const pm = await waitFor(() => {
    const el = section('pre-mortem')
    expect(el).toBeTruthy()
    expect(within(el!).getByText('1 of 4 answered')).toBeInTheDocument()
    return el!
  })
  const rows = within(pm).getAllByTestId('premortem-finding')
  expect(rows.map((r) => r.textContent)).toEqual([
    expect.stringContaining('The lists ship mostly empty.'),
    expect.stringContaining('The uses route scans every firing per request.'),
    expect.stringContaining('Counts drift between the views.'),
    expect.stringContaining('A fact with no line citation opens nowhere.'),
  ])
  expect(within(rows[0]!).getByText('FR-2')).toBeInTheDocument()
  expect(within(rows[1]!).getByText('FR-3')).toBeInTheDocument()
  const answer = within(rows[0]!).getByTestId('premortem-answer')
  expect(answer).toHaveTextContent('Each list now says why it is empty.')
  expect(answer).toHaveTextContent(/Answered by Architect · .+/)
  expect(rows.slice(1).every((r) => within(r).queryByTestId('premortem-unanswered'))).toBe(true)
  return pm
}

describe('document-tab-end (FR-7)', () => {
  it('the side panel ends its Document tab with the pre-mortem, and its Builds tab shows none', async () => {
    renderPanel()
    await expectFindings()
    // The pre-mortem is the Document tab's last section, after the requirements.
    const order = sections()
    expect(order[order.length - 1]).toBe('section-pre-mortem')
    expect(order.indexOf('section-requirements')).toBeLessThan(order.indexOf('section-pre-mortem'))
    fireEvent.click(screen.getByRole('radio', { name: /Builds/ }))
    await waitFor(() => expect(section('builds')).toBeTruthy())
    expect(section('pre-mortem')).toBeNull()
    expect(screen.queryByTestId('premortem-newest')).toBeNull()
  })

  it('the full spec page draws it after the requirements, before tasks and builds, once', async () => {
    renderPage()
    await expectFindings()
    await waitFor(() => expect(section('builds')).toBeTruthy())
    const order = sections()
    expect(order.filter((id) => id === 'section-pre-mortem')).toHaveLength(1)
    expect(order.indexOf('section-requirements')).toBeLessThan(order.indexOf('section-pre-mortem'))
    expect(order.indexOf('section-pre-mortem')).toBeLessThan(order.indexOf('section-tasks'))
    expect(order.indexOf('section-pre-mortem')).toBeLessThan(order.indexOf('section-builds'))
    // The outline lists it right after Requirements.
    const outline = screen.getByRole('navigation', { name: 'Outline' })
    const labels = within(outline).getAllByRole('button').map((b) => b.textContent ?? '')
    const req = labels.findIndex((l) => l.startsWith('Requirements'))
    expect(labels[req + 1]).toBe('Pre-mortem')
  })

  it('says no pre-mortem has run on a document never run, on both surfaces', async () => {
    hub.preMortems = []
    renderPanel()
    await waitFor(() => expect(within(section('pre-mortem')!).getByText('No pre-mortem has run yet.')).toBeInTheDocument())
    cleanup()
    renderPage()
    await waitFor(() => expect(within(section('pre-mortem')!).getByText('No pre-mortem has run yet.')).toBeInTheDocument())
    // With the job off it still says none has run, beside where to switch it on.
    cleanup()
    hub.jobOn = false
    renderPanel()
    await waitFor(() => expect(within(section('pre-mortem')!).getByTestId('premortem-off')).toBeInTheDocument())
    expect(within(section('pre-mortem')!).getByText('No pre-mortem has run yet.')).toBeInTheDocument()
  })

  it('says one is running while a firing of this document is in progress, on both surfaces', async () => {
    hub.preMortems = []
    hub.running = [{ run_id: 'run-1', job: 'pre-mortem', subject: { document: DOC_ID, path: PATH }, trigger: 'criteria_written', initiator: 'autonomous', started_at: '2026-11-23T22:49:00Z' }]
    renderPanel()
    await waitFor(() => expect(within(section('pre-mortem')!).getByTestId('premortem-running')).toHaveTextContent('A pre-mortem is running.'))
    cleanup()
    renderPage()
    await waitFor(() => expect(within(section('pre-mortem')!).getByTestId('premortem-running')).toBeInTheDocument())
  })
})

describe('possible-not-final (FR-10, the UI half)', () => {
  it('the full spec page shows the possible fact under its requirement, marked not confirmed', async () => {
    hub.possible = [POSSIBLE]
    renderPage()
    const aside = await screen.findByTestId('spec-possible-facts')
    expect(aside).toHaveTextContent(POSSIBLE.claim)
    expect(aside).toHaveTextContent('not confirmed')
    expect(document.querySelector('[data-anchor="FR-2"]')?.contains(aside)).toBe(true)
    expect(screen.getAllByTestId('spec-possible-facts')).toHaveLength(1)
  })

  it('the side panel does not show it', async () => {
    hub.possible = [POSSIBLE]
    renderPanel()
    await waitFor(() => expect(document.querySelector('[data-anchor="FR-2"]')).toBeTruthy())
    // The warnings route was read (the panel reads it for its health line) and still nothing shows.
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/vault/warnings'))).toBe(true))
    expect(screen.queryByTestId('spec-possible-facts')).toBeNull()
    expect(screen.queryByText(POSSIBLE.claim)).toBeNull()
  })

  it('a warnings read that failed says the possible facts could not be read, not that there are none', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (new URL(url).pathname.endsWith('/vault/warnings')) return new Response(JSON.stringify({ detail: 'vault check broke' }), { status: 500 })
        const body = route(url)
        if (body === undefined) return new Response(JSON.stringify({ detail: 'not stubbed' }), { status: 404 })
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }),
    )
    renderPage()
    // The warnings hook retries a failed read twice before it gives up.
    const notes = await screen.findAllByTestId('spec-possible-facts-unreadable', {}, { timeout: 8000 })
    expect(notes[0]).toHaveTextContent('Possible backing facts could not be read')
    expect(screen.queryByTestId('spec-possible-facts')).toBeNull()
  })
})
