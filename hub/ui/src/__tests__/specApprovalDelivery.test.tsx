/**
 * The stale-recommendation strip, Build and Approve and build opening with the recommended build,
 * and the approval report (`a-document-says-how-it-will-be-built-and-approval-starts-it`, tasks
 * 3.2-3.4; `exploring-ends-at-an-approved-plan`, criterion `recommendation-prefills`).
 *
 * Fed through the real `useSpec`/`useSpecDocuments`/`useDocumentFlow` and mutation hooks with
 * `getJson`/`postJson` mocked by path, the same pattern `startFlow.test.tsx` uses — so the report's
 * `useDocumentFlow` lookup runs over a `GET /loops`-shaped array, and the Build dialog is fed the
 * document read's real payload (`recommended_build`, `content_version`), not a hand-shaped prop
 * (F190).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { SpecApprovalReport } from '@/components/spec/SpecApprovalReport'
import { useConfigStore } from '@/store/configStore'
import type {
  SpecApprovalOutcome,
  SpecBuildOutcome,
  SpecDeliveryStatus,
  SpecRecommendedBuild,
} from '@/api/spec'

const posts: Array<{ path: string; body: unknown }> = []
let loops: unknown[] = []
let documents: unknown[] = []
let specDelivery: SpecDeliveryStatus | undefined
let specOutcome: SpecApprovalOutcome | undefined
let specBuilt: SpecBuildOutcome | undefined
let recommended: SpecRecommendedBuild | undefined

/** What `GET /project/spec` returns for a document that recommends a flow (`_recommended_build`). */
const RECOMMENDED: SpecRecommendedBuild = {
  mode: 'flow',
  agent: 'dev',
  reviewer: 'qa',
  tester: null,
  cron: '*/10 * * * *',
  stop_when_queue_empties: true,
  stop_at: null,
  // The build's settings, as `_recommended_build` resolves them for a flow delivery that names
  // none, on a sketch-rigor document (slice D).
  driver: 'flow',
  level: 'reviewed',
  builders: [],
  reviewers: [],
  lead: null,
  budget_cap_usd: null,
  landing: 'main',
  task_builders: {},
  reasons: {
    mode: 'The work splits into three tasks.',
    agent: 'dev built the module it changes.',
    reviewer: 'qa reviewed the last slice.',
  },
}

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return loops
      if (path.includes('/project/spec?')) {
        return {
          path: 'spec/changes/demo/spec.json',
          content: '<html></html>',
          updated_at: '2026-09-27T00:00:00Z',
          content_version: 'v1',
          ...(specDelivery ? { delivery_status: specDelivery } : {}),
          ...(specOutcome ? { approval_outcome: specOutcome } : {}),
          ...(specBuilt ? { build_outcome: specBuilt } : {}),
          ...(recommended ? { recommended_build: recommended } : {}),
        }
      }
      if (path.includes('/documents')) return { documents }
      return []
    }),
    postJson: vi.fn(async (path: string, body: unknown) => {
      posts.push({ path, body })
      return { id: 'job-new', build_outcome: { flow: { state: 'created', messages: ['started'] } } }
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'dev' }, { name: 'qa' }], isError: false }),
}))

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: 'spec/changes/demo/spec.json',
    title: 'Demo',
    kind: 'change-spec',
    phase: 'exploring',
    rigor: 'sketch',
    content_digest: null,
    explore_closed: true,
    updated_at: '2026-09-27T00:00:00Z',
    ...overrides,
  }
}

function loop(overrides: Record<string, unknown> = {}) {
  return {
    id: 'loop-1',
    label: 'Demo flow',
    agent: 'dev',
    spec_document_id: 'spdoc-1',
    ending_state: null,
    archived_at: null,
    ...overrides,
  }
}

function outcome(overrides: Partial<SpecApprovalOutcome> = {}): SpecApprovalOutcome {
  return {
    created: [],
    already_served: [],
    failed: null,
    dependencies_not_honoured: [],
    flow: { state: 'none', messages: [] },
    ...overrides,
  }
}

function renderPhaseBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path="spec/changes/demo/spec.json" />
    </QueryClientProvider>,
  )
}

function renderReport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecApprovalReport path="spec/changes/demo/spec.json" />
    </QueryClientProvider>,
  )
}

/** Both mounted together, the shape `SpecDocumentPanel` mounts them in. */
function renderPanelPair() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path="spec/changes/demo/spec.json" />
      <SpecApprovalReport path="spec/changes/demo/spec.json" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  posts.length = 0
  loops = []
  documents = [doc()]
  specDelivery = undefined
  specOutcome = undefined
  specBuilt = undefined
  recommended = undefined
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(() => cleanup())

/** The page has loaded the document read once Approve is enabled: it names that read's version. */
async function loaded() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled())
}

describe('the stale-recommendation strip', () => {
  it.each<[SpecDeliveryStatus['state'], SpecDeliveryStatus['reason'] | undefined]>([
    ['ok', undefined],
    ['none', undefined],
    ['absent', undefined],
  ])('does not appear for delivery_status.state = %s', async (state, reason) => {
    specDelivery = { state, agent: reason ? 'dev2' : undefined, reason }
    renderPhaseBar()
    await screen.findByTestId('spec-phase')
    expect(screen.queryByTestId('delivery-stale-strip')).not.toBeInTheDocument()
  })

  it('appears only for delivery_status.state = "stale", naming the archived agent', async () => {
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived' }
    renderPhaseBar()
    const strip = await screen.findByTestId('delivery-stale-strip')
    expect(strip).toHaveTextContent('The recommended build names dev2, which is archived')
    expect(strip).toHaveTextContent('Building will not start a flow unless you choose another agent')
  })

  it('names an unknown agent differently from an archived one', async () => {
    specDelivery = { state: 'stale', agent: 'ghost', reason: 'unknown' }
    renderPhaseBar()
    const strip = await screen.findByTestId('delivery-stale-strip')
    expect(strip).toHaveTextContent('names ghost, which is not an agent on this project')
  })
})

describe('Approve, Approve and build, and Build (recommendation-prefills)', () => {
  it('approves naming the loaded version, with no delivery_agent: approval starts nothing', async () => {
    recommended = RECOMMENDED
    renderPhaseBar()
    await loaded()

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].path).toContain('/documents/phase?')
    expect(posts[0].path).toContain('to=approved')
    expect(posts[0].body).toMatchObject({ content_version: 'v1' })
    expect(posts[0].body).not.toHaveProperty('delivery_agent')
  })

  it('opens Approve and build with the recommended agent, reviewer and reasons filled in', async () => {
    recommended = RECOMMENDED
    renderPhaseBar()
    await loaded()

    fireEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))

    const dialog = await screen.findByTestId('build-dialog')
    expect(within(dialog).getByTestId('build-agent')).toHaveValue('dev')
    expect(within(dialog).getByTestId('build-reason-agent')).toHaveTextContent(
      'dev built the module it changes.',
    )
    expect(within(dialog).getByTestId('build-reviewer')).toHaveTextContent('@qa')
    expect(within(dialog).getByTestId('build-reason-reviewer')).toHaveTextContent(
      'qa reviewed the last slice.',
    )
    expect(within(dialog).getByTestId('build-reason-mode')).toHaveTextContent('three tasks')
    expect(within(dialog).getByTestId('build-cron')).toHaveTextContent('*/10 * * * *')
  })

  it('approves and builds in one request, keeping the recommendation', async () => {
    recommended = RECOMMENDED
    renderPhaseBar()
    await loaded()

    fireEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))
    fireEvent.click(await screen.findByTestId('build-confirm'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].path).toContain('/documents/approve-and-build?')
    expect(posts[0].body).toMatchObject({ content_version: 'v1' })
    expect(posts[0].body).not.toHaveProperty('delivery_agent')
  })

  it('sends the agent the operator chose instead, or "" for no flow', async () => {
    recommended = RECOMMENDED
    renderPhaseBar()
    await loaded()

    fireEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))
    fireEvent.change(await screen.findByTestId('build-agent'), { target: { value: 'qa' } })
    fireEvent.click(screen.getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toMatchObject({ delivery_agent: 'qa' })

    fireEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))
    fireEvent.change(await screen.findByTestId('build-agent'), { target: { value: '__no_flow__' } })
    fireEvent.click(screen.getByTestId('build-confirm'))
    await waitFor(() => expect(posts).toHaveLength(2))
    expect(posts[1].body).toMatchObject({ delivery_agent: '' })
  })

  it('offers Build on an approved document, opening with the recommendation, later than approval', async () => {
    documents = [doc({ phase: 'approved' })]
    recommended = RECOMMENDED
    renderPhaseBar()

    fireEvent.click(await screen.findByRole('button', { name: 'Build…' }))
    const dialog = await screen.findByTestId('build-dialog')
    expect(within(dialog).getByTestId('build-agent')).toHaveValue('dev')
    fireEvent.click(within(dialog).getByTestId('build-confirm'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].path).toContain('/documents/build?')
    // Exactly the settings the dialog showed, the recommendation's; the agent kept is not sent.
    expect(posts[0].body).toEqual({
      driver: 'flow',
      level: 'reviewed',
      builders: [],
      reviewers: [],
      landing: 'main',
      task_builders: {},
    })
  })

  it('says when the document recommends no build', async () => {
    renderPhaseBar()
    await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))
    expect(await screen.findByTestId('build-no-recommendation')).toBeInTheDocument()
  })
})

describe('SpecApprovalReport', () => {
  it('renders nothing when approval_outcome is absent', async () => {
    specOutcome = undefined
    documents = [doc({ phase: 'approved' })]
    const { container } = renderReport()
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })

  it('lists created, already_served, failed, dependencies and flow messages in the fixture order', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = [loop()]
    specOutcome = outcome({
      created: [{ id: 't-1', key: 'T-1', title: 'Write the thing' }],
      already_served: [{ key: 'T-2', requirements: ['FR-9'] }],
      failed: 'RuntimeError: board blew up',
      dependencies_not_honoured: [
        { task_id: 't-3', task_key: 'T-3', reference: 'T-9', reason: 'not_declared' },
        { task_id: 't-4', task_key: 'T-4', reference: 'T-1', reason: 'cycle' },
      ],
      flow: { state: 'existing', name: 'Demo flow', agent: 'dev', messages: ['The flow Demo flow already builds this document.'] },
    })
    renderReport()

    const report = await screen.findByTestId('spec-approval-report')
    const text = report.textContent ?? ''
    const iCreated = text.indexOf('Write the thing')
    const iServed = text.indexOf('T-2')
    const iFailed = text.indexOf('board blew up')
    const iDep1 = text.indexOf('T-3')
    const iDep2 = text.indexOf('T-4')
    const iFlow = text.indexOf('already builds this document')

    expect(iCreated).toBeGreaterThanOrEqual(0)
    expect(iServed).toBeGreaterThan(iCreated)
    expect(iFailed).toBeGreaterThan(iServed)
    expect(iDep1).toBeGreaterThan(iFailed)
    expect(iDep2).toBeGreaterThan(iDep1)
    expect(iFlow).toBeGreaterThan(iDep2)
  })

  it('shows refreshed, closed-linking-retired and no-longer-declared tasks between failed and dependencies (F535)', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = [loop()]
    // The route's own key order: ..., failed, refreshed, closed_linking_retired, no_longer_declared,
    // dependencies_not_honoured, flow.
    specOutcome = outcome({
      failed: 'RuntimeError: partial',
      refreshed: [
        { id: 't-1', key: 'K-1', title: 'New title', fields: ['title', 'acceptance_criteria'], linked: ['FR-2', 'FR-3'], unlinked: ['FR-1'] },
      ],
      closed_linking_retired: [{ id: 't-2', key: 'K-2', status: 'approved', requirements: ['FR-1'] }],
      no_longer_declared: [{ id: 't-3', key: 'K-3', status: 'pending' }],
      dependencies_not_honoured: [{ task_id: 't-4', task_key: 'K-4', reference: 'K-9', reason: 'not_declared' }],
    })
    renderReport()

    const refreshed = await screen.findByTestId('approval-refreshed')
    expect(refreshed.textContent).toContain('K-1')
    expect(refreshed.textContent).toContain('New title')
    expect(refreshed.textContent).toContain('title, acceptance criteria')
    expect(refreshed.textContent).toContain('linked FR-2, FR-3')
    expect(refreshed.textContent).toContain('unlinked FR-1')
    const closed = screen.getByTestId('approval-closed-retired')
    expect(closed.textContent).toContain('K-2')
    expect(closed.textContent).toContain('FR-1')
    expect(screen.getByTestId('approval-no-longer-declared').textContent).toContain('K-3')

    const text = screen.getByTestId('spec-approval-report').textContent ?? ''
    const order = ['partial', 'K-1', 'K-2', 'K-3', 'K-4'].map((needle) => text.indexOf(needle))
    expect(order[0]).toBeGreaterThanOrEqual(0)
    for (let i = 1; i < order.length; i++) expect(order[i]).toBeGreaterThan(order[i - 1])
  })

  it('renders an outcome from a Hub that predates the refresh fields', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = [loop()]
    specOutcome = outcome({ created: [{ id: 't-1', key: 'T-1', title: 'Write the thing' }] })
    renderReport()
    await screen.findByTestId('approval-created')
    expect(screen.queryByTestId('approval-refreshed')).toBeNull()
  })

  it('points at Build… when nothing builds the approved document yet', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = []
    specOutcome = outcome({ flow: undefined })
    renderReport()

    await screen.findByTestId('spec-approval-report')
    expect(screen.getByTestId('approval-start-flow-pointer')).toHaveTextContent('use Build… above')
  })

  it('shows what the newest build did, and points at Start a flow… when it started none', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = []
    specOutcome = outcome({ flow: undefined })
    specBuilt = { flow: { state: 'not_created', messages: ['No flow was started: it has no open tasks to work.'] } }
    renderReport()

    expect(await screen.findByTestId('approval-flow-message')).toHaveTextContent('no open tasks to work')
    expect(screen.getByTestId('approval-start-flow-pointer')).toHaveTextContent('use Start a flow… above')
  })

  it('hides the pointer once an unarchived loop declares the document', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = [loop()]
    specOutcome = outcome({ flow: { state: 'created', name: 'Demo flow', agent: 'dev', messages: ['The flow Demo flow was created.'] } })
    renderReport()

    await screen.findByTestId('spec-approval-report')
    expect(screen.queryByTestId('approval-start-flow-pointer')).not.toBeInTheDocument()
  })

  it('never shows the pointer for a document that is not a change-spec', async () => {
    documents = [doc({ phase: 'approved', kind: 'roadmap' })]
    loops = []
    specOutcome = outcome({ flow: { state: 'not_applicable', messages: ['Only a change document declares a delivery.'] } })
    renderReport()

    await screen.findByTestId('spec-approval-report')
    expect(screen.queryByTestId('approval-start-flow-pointer')).not.toBeInTheDocument()
  })
})

describe('the panel has exactly one Build… control', () => {
  it('when the phase bar and the report are mounted side by side', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = []
    specOutcome = outcome({ flow: undefined })
    renderPanelPair()

    await screen.findByTestId('spec-build')
    const buttons = screen.getAllByText(/Build…/, { selector: 'button' })
    expect(buttons).toHaveLength(1)
    // The report's own mention is text, not a second control.
    expect(screen.getByTestId('approval-start-flow-pointer').querySelector('button')).toBeNull()
  })
})

describe('who reviews (F508)', () => {
  it('says any free agent reviews when the document names no reviewer', async () => {
    specDelivery = { state: 'ok', agent: 'dev' }
    renderPhaseBar()
    const line = await screen.findByTestId('delivery-reviewer')
    expect(line).toHaveTextContent('Reviewed by any free agent')
    expect(line).toHaveAttribute('data-stale', 'false')
  })

  it('names the default reviewer', async () => {
    specDelivery = { state: 'ok', agent: 'dev', reviewer: 'critic', reviewer_state: 'ok' }
    renderPhaseBar()
    const line = await screen.findByTestId('delivery-reviewer')
    expect(line).toHaveTextContent('Reviewed by @critic')
    expect(line).toHaveAttribute('data-stale', 'false')
  })

  it.each<['archived' | 'unknown', string]>([
    ['archived', 'which is archived'],
    ['unknown', 'which is not an agent on this project'],
  ])('flags a %s default reviewer and says the reviews come to the operator', async (state, words) => {
    specDelivery = { state: 'ok', agent: 'dev', reviewer: 'critic', reviewer_state: state }
    renderPhaseBar()
    const line = await screen.findByTestId('delivery-reviewer')
    expect(line).toHaveTextContent(`Reviewed by @critic, ${words}`)
    expect(line).toHaveTextContent('reviews will come to you')
    expect(line).toHaveAttribute('data-stale', 'true')
  })

  it('still says who reviews beside a stale builder', async () => {
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived', reviewer: 'critic', reviewer_state: 'ok' }
    renderPhaseBar()
    expect(await screen.findByTestId('delivery-reviewer')).toHaveTextContent('Reviewed by @critic')
  })

  it.each<SpecDeliveryStatus['state']>(['none', 'absent'])(
    'says nothing about reviewers when no flow is declared (%s)',
    async (state) => {
      specDelivery = { state }
      renderPhaseBar()
      await screen.findByTestId('spec-phase')
      expect(screen.queryByTestId('delivery-reviewer')).not.toBeInTheDocument()
    },
  )
})
