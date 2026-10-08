/**
 * The stale-delivery strip, sending the operator's choice with Approve, and the approval report
 * (`a-document-says-how-it-will-be-built-and-approval-starts-it`, tasks 3.2/3.3, task 3.4).
 *
 * Fed through the real `useSpec`/`useSpecDocuments`/`useDocumentFlow`/`useSetSpecPhase` hooks with
 * `getJson`/`postJson` mocked by path, the same pattern `startFlow.test.tsx` uses for the sibling
 * change — so the report's `useDocumentFlow` lookup runs over a `GET /loops`-shaped array, not a
 * hand-shaped fixture the route never returns (F190).
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { SpecApprovalReport } from '@/components/spec/SpecApprovalReport'
import { useConfigStore } from '@/store/configStore'
import type { SpecApprovalOutcome, SpecDeliveryStatus } from '@/api/spec'

const posts: Array<{ path: string; body: unknown }> = []
let loops: unknown[] = []
let documents: unknown[] = []
let specDelivery: SpecDeliveryStatus | undefined
let specOutcome: SpecApprovalOutcome | undefined

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async (path: string) => {
      if (path.includes('/loops')) return loops
      if (path.includes('/project/spec?')) {
        return {
          path: 'spec/changes/demo/spec.html',
          content: '<html></html>',
          updated_at: '2026-09-27T00:00:00Z',
          ...(specDelivery ? { delivery_status: specDelivery } : {}),
          ...(specOutcome ? { approval_outcome: specOutcome } : {}),
        }
      }
      if (path.includes('/documents')) return { documents }
      return []
    }),
    postJson: vi.fn(async (path: string, body: unknown) => {
      posts.push({ path, body })
      return { id: 'job-new' }
    }),
  }
})
vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'dev' }, { name: 'qa' }], isError: false }),
}))

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: 'spec/changes/demo/spec.html',
    title: 'Demo',
    kind: 'change-spec',
    phase: 'proposed',
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
      <SpecPhaseBar path="spec/changes/demo/spec.html" />
    </QueryClientProvider>,
  )
}

function renderReport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecApprovalReport path="spec/changes/demo/spec.html" />
    </QueryClientProvider>,
  )
}

/** Both mounted together, the shape `SpecDocumentPanel` mounts them in — enough to check there is
 *  exactly one Start a flow… control between the two, without pulling in `SpecFrame`'s iframe
 *  bridge and the panel's other unrelated children. */
function renderPanelPair() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path="spec/changes/demo/spec.html" />
      <SpecApprovalReport path="spec/changes/demo/spec.html" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  posts.length = 0
  loops = []
  documents = [doc()]
  specDelivery = undefined
  specOutcome = undefined
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(() => cleanup())

describe('the stale-delivery strip', () => {
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
    expect(strip).toHaveTextContent('Delivery names dev2, which is archived')
    expect(strip).toHaveTextContent('Approving will not start a flow unless you choose another agent')
  })

  it('names an unknown agent differently from an archived one', async () => {
    specDelivery = { state: 'stale', agent: 'ghost', reason: 'unknown' }
    renderPhaseBar()
    const strip = await screen.findByTestId('delivery-stale-strip')
    expect(strip).toHaveTextContent('Delivery names ghost, which is not an agent on this project')
  })

  it('offers the open agents and "No flow" in the select', async () => {
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived' }
    renderPhaseBar()
    await screen.findByTestId('delivery-stale-strip')
    const select = screen.getByTestId('delivery-agent-choice') as HTMLSelectElement
    const optionLabels = Array.from(select.options).map((o) => o.textContent)
    expect(optionLabels).toContain('@dev')
    expect(optionLabels).toContain('@qa')
    expect(optionLabels).toContain('No flow')
  })
})

describe('Approve and the chosen delivery agent', () => {
  it('sends no delivery_agent when the operator made no choice', async () => {
    documents = [doc({ phase: 'proposed' })]
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived' }
    renderPhaseBar()
    await screen.findByTestId('delivery-stale-strip')

    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).not.toHaveProperty('delivery_agent')
  })

  it('sends the chosen agent name when the operator picked one', async () => {
    documents = [doc({ phase: 'proposed' })]
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived' }
    renderPhaseBar()
    await screen.findByTestId('delivery-stale-strip')

    fireEvent.change(screen.getByTestId('delivery-agent-choice'), { target: { value: 'qa' } })
    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].path).toContain('to=approved')
    expect(posts[0].body).toMatchObject({ delivery_agent: 'qa' })
  })

  it('sends delivery_agent: "" when the operator chose "No flow"', async () => {
    documents = [doc({ phase: 'proposed' })]
    specDelivery = { state: 'stale', agent: 'dev2', reason: 'archived' }
    renderPhaseBar()
    await screen.findByTestId('delivery-stale-strip')

    fireEvent.change(screen.getByTestId('delivery-agent-choice'), { target: { value: '' } })
    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).toMatchObject({ delivery_agent: '' })
  })

  it('sends no delivery_agent at all on an ordinary (non-stale) approval', async () => {
    documents = [doc({ phase: 'proposed' })]
    specDelivery = { state: 'ok', agent: 'dev' }
    renderPhaseBar()
    await screen.findByTestId('spec-phase')

    fireEvent.click(screen.getByText('Approve'))

    await waitFor(() => expect(posts).toHaveLength(1))
    expect(posts[0].body).not.toHaveProperty('delivery_agent')
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

  it('shows the "use Start a flow… above" pointer when no unarchived loop declares the document', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = []
    specOutcome = outcome({ flow: { state: 'not_created', messages: ['No flow was started: the approval gave it no tasks. Start a flow… once there is work.'] } })
    renderReport()

    await screen.findByTestId('spec-approval-report')
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

describe('the panel has exactly one Start a flow… control', () => {
  it('when the phase bar and the report are mounted side by side', async () => {
    documents = [doc({ phase: 'approved' })]
    loops = []
    specOutcome = outcome({ flow: { state: 'not_created', messages: ['No flow was started: the approval gave it no tasks. Start a flow… once there is work.'] } })
    renderPanelPair()

    await screen.findByTestId('spec-start-flow')
    const buttons = screen.getAllByText(/Start a flow…/, { selector: 'button' })
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
