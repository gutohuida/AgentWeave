import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'

/** The decisions other than the one primary action live in the header's overflow menu. */
async function openMore() {
  await userEvent.click(screen.getByRole('button', { name: 'More actions' }))
}
async function chooseMore(name: string | RegExp) {
  await openMore()
  await userEvent.click(await screen.findByRole('menuitem', { name }))
}

/**
 * The controls an operator has and an agent does not.
 *
 * `importOriginal` is used so this file does not join the nine that replace a
 * whole api module with a bare object — a partial mock keeps the rest of the
 * module's exports real, so a rename elsewhere fails loudly here.
 */
const setJourney = vi.fn()
const check = vi.fn()
const setPhase = vi.fn()
const reloadSpec = vi.fn()
/** The document read the page shows: `content_version` is what an approval names. */
let specDoc: unknown = { path: 'spec/changes/demo/spec.json', content: '', content_version: 'v1' }
let documents: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSetSpecJourney: () => ({ mutate: setJourney, isPending: false }),
    useSpec: () => ({ data: specDoc, isError: false, refetch: reloadSpec }),
    useCheckSpecDocument: () => ({ mutateAsync: check, isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
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
  documents = [doc()]
  specDoc = { path: 'spec/changes/demo/spec.json', content: '', content_version: 'v1' }
  check.mockResolvedValue({ ...doc(), blocking: [], warnings: [], ready: true, content_version: 'v1' })
})

describe('SpecPhaseBar', () => {
  it('shows the phase the Hub reports, not one read from the document', () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()
    expect(screen.getByTestId('spec-phase')).toHaveAttribute('data-phase', 'approved')
    expect(screen.getByTestId('spec-phase')).toHaveTextContent(/^approved$/i)
  })

  it('renders nothing for a path the Hub does not track', () => {
    documents = []
    const { container } = renderBar()
    expect(container).toBeEmptyDOMElement()
  })

  it('offers Check, Approve and Approve and build while exploring, and no Propose', () => {
    renderBar()
    expect(screen.getByRole('button', { name: 'Check' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve and build…' })).toBeInTheDocument()
    expect(screen.queryByText('Propose')).not.toBeInTheDocument()
    expect(screen.queryByText('Exploration is complete')).not.toBeInTheDocument()
  })

  it('checks without moving anything: the phase route is never called', async () => {
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))
    expect(check).toHaveBeenCalledWith({ path: 'spec/changes/demo/spec.json' })
    expect(setPhase).not.toHaveBeenCalled()
    expect(await screen.findByTestId('spec-check-clean')).toHaveTextContent('nothing blocks approval')
  })

  describe('the journey (step-journey FR-10)', () => {
    const SMALL = ['intake', 'requirements-and-acceptance', 'tasks', 'build']
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
      expect(within(screen.getByTestId('spec-journey-size')).getByRole('radio', { name: 'Small' })).toHaveAttribute('aria-checked', 'true')
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
      await userEvent.click(within(screen.getByTestId('spec-journey-size')).getByRole('radio', { name: 'Large' }))
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

    it('is absent once the document is approved, and on a roadmap', () => {
      documents = [doc({ phase: 'approved', step: 'build', size: 'small', journey: SMALL })]
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
    check.mockResolvedValue({
      ...doc(),
      warnings: [],
      ready: false,
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

    await userEvent.click(screen.getByRole('button', { name: 'Check' }))

    await waitFor(() => {
      expect(screen.getByText(/state what is out of scope/)).toBeInTheDocument()
    })
    expect(screen.getByText(/has no task/)).toBeInTheDocument()
    expect(screen.getByText('scope.non_goals')).toBeInTheDocument()
  })

  it('offers approval straight from exploring', () => {
    renderBar()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
  })

  it('does not offer approval once approved; it offers Build', () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Build…' })).toBeInTheDocument()
  })

  it('approves through the phase route naming the version it shows', async () => {
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(setPhase).toHaveBeenCalledWith(
      { path: 'spec/changes/demo/spec.json', to: 'approved', content_version: 'v1' },
      expect.anything(),
    )
  })

  it('says the document changed since it was loaded, and reloads it', async () => {
    setPhase.mockImplementation((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(
        new ApiError(
          409,
          JSON.stringify({
            detail: {
              code: 'document_changed',
              message: 'the document changed since it was loaded; reload it, read what changed, and approve again',
            },
          }),
        ),
      )
    })
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(screen.getByTestId('spec-blocking')).toHaveTextContent('changed since it was loaded')
    expect(reloadSpec).toHaveBeenCalled()
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
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

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
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(screen.getByText(/the payload is broken/)).toBeInTheDocument()
  })

  it('can reopen an approved document', async () => {
    documents = [doc({ phase: 'approved', explore_closed: true })]
    renderBar()

    await chooseMore('Reopen for changes')

    // With a callback since ui-finesse: the outcome is said in a toast either way.
    expect(setPhase).toHaveBeenCalledWith(
      { path: 'spec/changes/demo/spec.json', to: 'exploring' },
      expect.objectContaining({ onError: expect.any(Function) }),
    )
  })

  it('does not offer reopening a document that is already exploring', async () => {
    renderBar()
    await openMore()
    expect(screen.queryByRole('menuitem', { name: /Reopen/ })).not.toBeInTheDocument()
  })

  // F205: `spec_lifecycle.TRANSITIONS` has an archive edge from `exploring` as well, added for
  // F37's empty mistaken document, and no screen offered it.
  it.each(['approved', 'exploring'])('offers archiving a %s document', async (phase) => {
    documents = [doc({ phase })]
    renderBar()
    await openMore()
    expect(screen.getByRole('menuitem', { name: 'Archive' })).toBeInTheDocument()
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

    await chooseMore('Archive')
    await userEvent.click(within(screen.getByRole('dialog')).getByText('Archive'))

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('alert')).toHaveTextContent('would retire work that still exists')
  })

  it('asks for confirmation before archiving, naming the document', async () => {
    documents = [doc({ phase: 'approved', title: 'Demo' })]
    renderBar()

    await chooseMore('Archive')

    expect(setPhase).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Demo')
    expect(dialog).toHaveTextContent('cannot be undone')
  })

  it('leaves the phase untouched when the archive confirmation is cancelled', async () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()

    await chooseMore('Archive')
    await userEvent.click(screen.getByText('Cancel'))

    expect(setPhase).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('archives through the phase route once the confirmation is confirmed', async () => {
    documents = [doc({ phase: 'approved' })]
    renderBar()

    await chooseMore('Archive')
    await userEvent.click(within(screen.getByRole('dialog')).getByText('Archive'))

    expect(setPhase).toHaveBeenCalledWith(
      { path: 'spec/changes/demo/spec.json', to: 'archived' },
      expect.anything(),
    )
  })

  it.each(['archived', 'current'])(
    'does not offer archiving a %s document',
    async (phase) => {
      documents = [doc({ phase })]
      renderBar()
      await openMore()
      expect(screen.queryByRole('menuitem', { name: 'Archive' })).not.toBeInTheDocument()
    },
  )

  it.each(['archived', 'current'])('does not offer reopening a %s document', async (phase) => {
    documents = [doc({ phase })]
    renderBar()
    await openMore()
    expect(screen.queryByRole('menuitem', { name: /Reopen/ })).not.toBeInTheDocument()
  })

  it.each(['exploring', 'approved', 'archived', 'current'])(
    'renders the literal phase name for %s',
    (phase) => {
      documents = [doc({ phase })]
      renderBar()
      expect(screen.getByTestId('spec-phase')).toHaveAttribute('data-phase', phase)
      expect(screen.getByTestId('spec-phase')).toHaveTextContent(new RegExp(`^${phase}$`, 'i'))
    },
  )
})
