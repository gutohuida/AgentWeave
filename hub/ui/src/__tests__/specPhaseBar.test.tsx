import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'

/**
 * The controls an operator has and an agent does not.
 *
 * `importOriginal` is used so this file does not join the nine that replace a
 * whole api module with a bare object — a partial mock keeps the rest of the
 * module's exports real, so a rename elsewhere fails loudly here.
 */
const setJourney = vi.fn()
const propose = vi.fn()
const setPhase = vi.fn()
const setRigor = vi.fn()
let documents: unknown[] = []
/** `GET /documents/{path}/rigor-history` answers **oldest first** (`spec_rigor.history_for` orders
 *  by `created_at, id` ascending; pinned by `test_the_rigor_history_route_answers_oldest_first`).
 *  Every fixture here is in that order (F190). */
let rigorEvents: unknown[] = []
let rigorHistoryError: unknown = null

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSetSpecJourney: () => ({ mutate: setJourney, isPending: false }),
    useProposeSpecDocument: () => ({ mutateAsync: propose, isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
    useSetSpecRigor: () => ({ mutateAsync: setRigor, isPending: false }),
    useSpecRigorHistory: () =>
      rigorHistoryError
        ? { data: undefined, error: rigorHistoryError }
        : { data: { events: rigorEvents }, error: null },
  }
})

function renderBar(path = 'spec/changes/demo/spec.json') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={path} />
    </QueryClientProvider>,
  )
}

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: 'spec/changes/demo/spec.json',
    title: 'Demo',
    kind: 'change-spec',
    phase: 'exploring',
    explore_closed: false,
    updated_at: '2026-08-12T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  setPhase.mockReset()
  setRigor.mockReset()
  setRigor.mockResolvedValue(doc())
  rigorEvents = []
  rigorHistoryError = null
  documents = [doc()]
  propose.mockResolvedValue({ ...doc(), blocking: [] })
})

describe('SpecPhaseBar', () => {
  it('shows the phase the Hub reports, not one read from the document', () => {
    documents = [doc({ phase: 'proposed' })]
    renderBar()
    expect(screen.getByTestId('spec-phase')).toHaveTextContent('proposed')
  })

  it('renders nothing for a path the Hub does not track', () => {
    documents = []
    const { container } = renderBar()
    expect(container).toBeEmptyDOMElement()
  })

  it('offers proposing while exploring, with no Exploration is complete control (FR-11)', () => {
    renderBar()
    expect(screen.getByText('Propose')).toBeInTheDocument()
    expect(screen.queryByText('Exploration is complete')).not.toBeInTheDocument()
  })

  describe('the journey (step-journey FR-10)', () => {
    const SMALL = ['intake', 'requirements-and-acceptance', 'tasks', 'delivery']
    const exploring = () =>
      doc({ step: 'requirements-and-acceptance', size: 'small', journey: SMALL })

    it('shows the journey in order with the current step marked, and the size', () => {
      documents = [exploring()]
      renderBar()
      const steps = within(screen.getByTestId('spec-journey'))
        .getAllByRole('button')
        .map((b) => b.getAttribute('data-testid'))
      expect(steps).toEqual(SMALL.map((s) => `spec-journey-step-${s}`))
      expect(screen.getByTestId('spec-journey-step-requirements-and-acceptance')).toHaveAttribute(
        'aria-current',
        'step',
      )
      expect(screen.getByTestId('spec-journey-step-intake')).not.toHaveAttribute('aria-current')
      expect(screen.getByTestId('spec-journey-size')).toHaveValue('small')
    })

    it('moves the document to any step, back or forward', async () => {
      documents = [exploring()]
      renderBar()
      await userEvent.click(screen.getByTestId('spec-journey-step-intake'))
      expect(setJourney).toHaveBeenCalledWith(
        { path: 'spec/changes/demo/spec.json', step: 'intake' },
        expect.anything(),
      )
    })

    it('changes the size', async () => {
      documents = [exploring()]
      renderBar()
      await userEvent.selectOptions(screen.getByTestId('spec-journey-size'), 'large')
      expect(setJourney).toHaveBeenCalledWith(
        { path: 'spec/changes/demo/spec.json', size: 'large' },
        expect.anything(),
      )
    })

    it('says so when a move is refused', async () => {
      documents = [exploring()]
      setJourney.mockImplementation((_args, opts: { onError: (e: unknown) => void }) =>
        opts.onError(new ApiError(409, '{"detail": "only an exploring change has a journey"}')),
      )
      renderBar()
      await userEvent.click(screen.getByTestId('spec-journey-step-tasks'))
      expect(await screen.findByTestId('spec-journey-refusal')).toHaveTextContent(
        'only an exploring change has a journey',
      )
    })

    it('is absent once the document is proposed, and on a roadmap', () => {
      documents = [doc({ phase: 'proposed', step: 'delivery', size: 'small', journey: SMALL })]
      const { unmount } = renderBar()
      expect(screen.queryByTestId('spec-journey')).not.toBeInTheDocument()
      unmount()
      documents = [doc({ kind: 'roadmap', step: null, size: null, journey: null })]
      renderBar()
      expect(screen.queryByTestId('spec-journey')).not.toBeInTheDocument()
    })
  })

  it('lists every blocking finding rather than the first', async () => {
    documents = [doc({ explore_closed: true })]
    propose.mockResolvedValue({
      ...doc(),
      blocking: [
        { code: 'non_goals_empty', where: 'scope.non_goals', message: 'state what is out of scope' },
        {
          code: 'requirement_without_task',
          where: 'requirements[0]',
          message: "'alpha' has no task",
        },
      ],
    })
    renderBar()

    await userEvent.click(screen.getByText('Propose'))

    await waitFor(() => {
      expect(screen.getByText(/state what is out of scope/)).toBeInTheDocument()
    })
    expect(screen.getByText(/has no task/)).toBeInTheDocument()
    expect(screen.getByText('scope.non_goals')).toBeInTheDocument()
  })

  it('offers approval only on a proposed document', () => {
    documents = [doc({ phase: 'proposed' })]
    renderBar()
    expect(screen.getByText('Approve')).toBeInTheDocument()
  })

  it('does not offer approval while exploring', () => {
    renderBar()
    expect(screen.queryByText('Approve')).not.toBeInTheDocument()
  })

  it('approves through the phase route, which has no agent-facing equivalent', async () => {
    documents = [doc({ phase: 'proposed' })]
    renderBar()

    await userEvent.click(screen.getByText('Approve'))

    expect(setPhase).toHaveBeenCalledWith(
      { path: 'spec/changes/demo/spec.json', to: 'approved' },
      expect.anything(),
    )
  })

  // F207: approval re-runs the completeness checks and answers 409 with every finding.
  it('shows each finding when approval is refused as incomplete', async () => {
    const refusal = new ApiError(
      409,
      JSON.stringify({
        detail: {
          code: 'document_incomplete',
          message: 'this document cannot move to approved yet: requirement_without_task',
          blocking: [
            { code: 'requirement_without_task', where: 'requirements[0]', message: "'alpha' has no task" },
            { code: 'non_goals_empty', where: 'scope.non_goals', message: 'state what is out of scope' },
          ],
        },
      }),
    )
    setPhase.mockImplementation((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(refusal)
    })
    documents = [doc({ phase: 'proposed' })]
    renderBar()

    await userEvent.click(screen.getByText('Approve'))

    expect(screen.getByText('requirements[0]')).toBeInTheDocument()
    expect(screen.getByText(/'alpha' has no task/)).toBeInTheDocument()
    expect(screen.getByText('scope.non_goals')).toBeInTheDocument()
  })

  it('renders a bare refusal message when approval fails without findings', async () => {
    setPhase.mockImplementation((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(
        new ApiError(422, JSON.stringify({ detail: { code: 'payload_invalid', message: 'the payload is broken' } })),
      )
    })
    documents = [doc({ phase: 'proposed' })]
    renderBar()

    await userEvent.click(screen.getByText('Approve'))

    expect(screen.getByText(/the payload is broken/)).toBeInTheDocument()
  })

  it('can reopen an approved document', async () => {
    documents = [doc({ phase: 'approved', explore_closed: true })]
    renderBar()

    await userEvent.click(screen.getByText('Reopen'))

    expect(setPhase).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.json',
      to: 'exploring',
    })
  })

  it('does not offer reopening a document that is already exploring', () => {
    renderBar()
    expect(screen.queryByText('Reopen')).not.toBeInTheDocument()
  })

  // F205: `spec_lifecycle.TRANSITIONS` has archive edges from `exploring` and `proposed` as well,
  // added for F37's empty mistaken document, and no screen offered them.
  it.each(['approved', 'exploring', 'proposed'])('offers archiving a %s document', (phase) => {
    documents = [doc({ phase })]
    renderBar()
    expect(screen.getByText('Archive')).toBeInTheDocument()
  })

  it("shows the Hub's refusal in the dialog when the document has produced work", async () => {
    const refusal = new ApiError(409, JSON.stringify({
      detail: {
        code: 'archive_would_orphan_work',
        message: 'this document has produced requirements or tasks, so archiving it from exploring would retire work that still exists. Approve it and archive that, or reopen it and decide about the work first.',
      },
    }))
    setPhase.mockImplementation((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(refusal)
    })
    documents = [doc({ phase: 'exploring' })]
    renderBar()

    await userEvent.click(screen.getByText('Archive'))
    await userEvent.click(within(screen.getByRole('dialog')).getByText('Archive'))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('alert')).toHaveTextContent('would retire work that still exists')
  })

  it('asks for confirmation before archiving, naming the document', async () => {
    documents = [doc({ phase: 'approved', title: 'Demo' })]
    renderBar()

    await userEvent.click(screen.getByText('Archive'))

    expect(setPhase).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Demo')
    expect(dialog).toHaveTextContent('cannot be undone')
  })

  it('leaves the phase untouched when the archive confirmation is cancelled', async () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()

    await userEvent.click(screen.getByText('Archive'))
    await userEvent.click(screen.getByText('Cancel'))

    expect(setPhase).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('archives through the phase route once the confirmation is confirmed', async () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()

    await userEvent.click(screen.getByText('Archive'))
    await userEvent.click(within(screen.getByRole('dialog')).getByText('Archive'))

    expect(setPhase).toHaveBeenCalledWith(
      { path: 'spec/changes/demo/spec.json', to: 'archived' },
      expect.anything(),
    )
  })

  it.each(['archived', 'current'])(
    'does not offer archiving a %s document',
    (phase) => {
      documents = [doc({ phase })]
      renderBar()
      expect(screen.queryByText('Archive')).not.toBeInTheDocument()
    },
  )

  it.each(['archived', 'current'])('does not offer reopening a %s document', (phase) => {
    documents = [doc({ phase })]
    renderBar()
    expect(screen.queryByText('Reopen')).not.toBeInTheDocument()
  })

  it.each(['exploring', 'proposed', 'approved', 'archived', 'current'])(
    'renders the literal phase name for %s',
    (phase) => {
      documents = [doc({ phase })]
      renderBar()
      expect(screen.getByTestId('spec-phase')).toHaveTextContent(phase)
    },
  )
})

/*
 * The rigor history, and the reason a rigor change carries (F211, F429;
 * `a-documents-rigor-history-and-retired-requirements-are-on-screen`).
 */
describe('SpecPhaseBar — rigor history and the reason for a change', () => {
  const PATH = 'spec/changes/demo/spec.json'

  function event(id: string, from: string, to: string, reason: string, createdAt: string) {
    return { id, from, to, actor_kind: 'operator', actor: 'operator', reason, created_at: createdAt }
  }

  // 1.2 (D1, F190). The fixture is in the route's order, oldest first. The list shows newest
  // first, so `contract → gate` leads. A component that did not reverse — or a fixture reversed
  // into an order the route never emits — fails the first assertion on the list.
  it('lists the history newest first from the route\'s oldest-first answer', async () => {
    documents = [doc({ rigor: 'gate', content_digest: 'abc' })]
    rigorEvents = [
      event('sre-1', 'sketch', 'contract', '', '2026-09-24T10:00:00+00:00'),
      event('sre-2', 'contract', 'gate', 'ready to enforce', '2026-09-24T11:00:00+00:00'),
    ]
    renderBar()

    const toggle = screen.getByTestId('spec-rigor-history-toggle')
    expect(toggle).toHaveTextContent('History (2)')
    await userEvent.click(toggle)

    const items = within(screen.getByTestId('spec-rigor-history')).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('contract → gate')
    expect(items[0]).toHaveTextContent('ready to enforce')
    expect(items[1]).toHaveTextContent('sketch → contract')
    expect(items[1]).toHaveTextContent('no reason given')
    expect(items[0]).toHaveTextContent('operator')
  })

  it('offers no history toggle when the rigor has never changed', () => {
    documents = [doc({ rigor: 'sketch' })]
    rigorEvents = []
    renderBar()
    expect(screen.queryByTestId('spec-rigor-history-toggle')).not.toBeInTheDocument()
  })

  // D5: a failed history read is said, and not mistaken for "never changed" (no toggle).
  it('says the history could not be loaded when its read fails', () => {
    documents = [doc({ rigor: 'gate' })]
    rigorHistoryError = new ApiError(500, 'database is locked')
    renderBar()
    expect(screen.getByTestId('spec-rigor-history-error')).toHaveTextContent('database is locked')
    expect(screen.queryByTestId('spec-rigor-history-toggle')).not.toBeInTheDocument()
  })

  // 1.3 (D2). A demotion does not post on change; it asks why, and cannot be confirmed blank.
  it('asks for a reason before lowering a gate, and sends it', async () => {
    documents = [doc({ rigor: 'gate', content_digest: 'abc' })]
    renderBar()

    await userEvent.selectOptions(screen.getByTestId('spec-rigor'), 'sketch')

    expect(setRigor).not.toHaveBeenCalled()
    const row = screen.getByTestId('spec-rigor-confirm')
    expect(row).toHaveTextContent('Change enforcement from Gate to Sketch?')
    const confirm = within(row).getByRole('button', { name: 'Confirm' })
    expect(confirm).toBeDisabled()

    // Whitespace is not a reason.
    const reason = within(row).getByRole('textbox')
    await userEvent.type(reason, '   ')
    expect(confirm).toBeDisabled()

    await userEvent.clear(reason)
    await userEvent.type(reason, 'shipping today')
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)

    expect(setRigor).toHaveBeenCalledWith({
      path: PATH,
      rigor: 'sketch',
      reason: 'shipping today',
      expectedDigest: 'abc',
    })
  })

  // 1.4 (D2). A promotion offers the field and does not require it.
  it('lets a promotion be confirmed with the reason left empty', async () => {
    documents = [doc({ rigor: 'sketch', content_digest: 'abc' })]
    renderBar()

    await userEvent.selectOptions(screen.getByTestId('spec-rigor'), 'gate')

    expect(setRigor).not.toHaveBeenCalled()
    const row = screen.getByTestId('spec-rigor-confirm')
    expect(within(row).getByRole('textbox')).toHaveValue('')
    const confirm = within(row).getByRole('button', { name: 'Confirm' })
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)

    expect(setRigor).toHaveBeenCalledWith({
      path: PATH,
      rigor: 'gate',
      reason: '',
      expectedDigest: 'abc',
    })
  })

  it('changes nothing when the confirmation is cancelled', async () => {
    documents = [doc({ rigor: 'sketch', content_digest: 'abc' })]
    renderBar()

    await userEvent.selectOptions(screen.getByTestId('spec-rigor'), 'gate')
    await userEvent.click(
      within(screen.getByTestId('spec-rigor-confirm')).getByRole('button', { name: 'Cancel' }),
    )

    expect(setRigor).not.toHaveBeenCalled()
    expect(screen.queryByTestId('spec-rigor-confirm')).not.toBeInTheDocument()
    expect((screen.getByTestId('spec-rigor') as HTMLSelectElement).value).toBe('sketch')
  })

  // 1.5 (D2) control. The refusal display is kept; it now arrives after Confirm.
  it('still lists every blocking line when the confirmed change is refused', async () => {
    setRigor.mockRejectedValue(
      new ApiError(
        409,
        JSON.stringify({
          detail: {
            code: 'document_not_enforceable',
            message: 'this document cannot be enforced as it stands',
            blocking: ['these requirements hold no identifier yet: alpha', 'FR-3 has no statement'],
          },
        }),
      ),
    )
    documents = [doc({ rigor: 'sketch', content_digest: 'abc' })]
    renderBar()

    await userEvent.selectOptions(screen.getByTestId('spec-rigor'), 'gate')
    await userEvent.click(
      within(screen.getByTestId('spec-rigor-confirm')).getByRole('button', { name: 'Confirm' }),
    )

    const refusal = await screen.findByTestId('spec-rigor-refusal')
    expect(refusal).toHaveTextContent('hold no identifier yet: alpha')
    expect(refusal).toHaveTextContent('FR-3 has no statement')
  })
})
