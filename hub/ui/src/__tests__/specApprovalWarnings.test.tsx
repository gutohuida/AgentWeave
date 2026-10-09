import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'

/**
 * Approval lists what is missing and can approve anyway (`approve-lists-what-is-missing-and-can-
 * approve-anyway`, FR-7). The 409 is the shape `POST /documents/phase` answers
 * (`hub/tests/test_approval_warnings_routes.py`): `{detail: {code: 'approval_warnings', message,
 * warnings: [{code, where, message}]}}`, the gaps in the order `phase_findings` lists them — the
 * completeness findings first, `steps_skipped` last.
 */
const propose = vi.fn()
const setPhase = vi.fn()
let documents: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSetSpecJourney: () => ({ mutate: vi.fn(), isPending: false }),
    useProposeSpecDocument: () => ({ mutateAsync: propose, isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
    useSetSpecRigor: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSpecRigorHistory: () => ({ data: { events: [] }, error: null }),
  }
})

const PATH = 'spec/changes/demo/spec.json'

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={PATH} />
    </QueryClientProvider>,
  )
}

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: PATH,
    title: 'Demo',
    kind: 'change-spec',
    phase: 'proposed',
    rigor: 'contract',
    content_digest: null,
    explore_closed: true,
    updated_at: '2026-10-09T00:00:00Z',
    ...overrides,
  }
}

const criterionGaps = ['alpha', 'beta', 'gamma', 'delta', 'epsilon'].map((key) => ({
  code: 'requirement_without_criterion',
  where: `requirements.${key}`,
  message: `MUST requirement '${key}' has no acceptance criterion`,
}))
const skipped = {
  code: 'steps_skipped',
  where: 'step',
  message: 'the document never reached: acceptance, tasks',
}

function refuseWithGaps() {
  setPhase.mockImplementationOnce((_vars: unknown, options: { onError: (e: unknown) => void }) => {
    options.onError(
      new ApiError(
        409,
        JSON.stringify({
          detail: {
            code: 'approval_warnings',
            message: 'this document has gaps; approve anyway to approve it',
            warnings: [...criterionGaps, skipped],
          },
        }),
      ),
    )
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  setPhase.mockReset()
  documents = [doc()]
})

describe('SpecPhaseBar approval warnings', () => {
  it('groups the gaps by code: one line each, with its count and up to three places', async () => {
    refuseWithGaps()
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    const list = await screen.findByTestId('approval-warnings')
    const lines = within(list).getAllByTestId(/^approval-warning-/)
    expect(lines.map((line) => line.dataset.testid)).toEqual([
      'approval-warning-requirement_without_criterion',
      'approval-warning-steps_skipped',
    ])
    const first = lines[0]
    expect(first).toHaveTextContent('5')
    expect(first).toHaveTextContent('requirements.alpha')
    expect(first).toHaveTextContent('requirements.gamma')
    expect(first).not.toHaveTextContent('requirements.delta')
    expect(first).toHaveTextContent('2 more')
    expect(lines[1]).toHaveTextContent('acceptance, tasks')
  })

  it('Approve anyway resends the approval with approve_anyway and clears the list on success', async () => {
    refuseWithGaps()
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await screen.findByTestId('approval-warnings')

    setPhase.mockImplementationOnce((_vars: unknown, options: { onSuccess: (r: unknown) => void }) => {
      options.onSuccess({ ...doc({ phase: 'approved' }) })
    })
    await userEvent.click(screen.getByRole('button', { name: 'Approve anyway' }))

    expect(setPhase).toHaveBeenLastCalledWith(
      { path: PATH, to: 'approved', approve_anyway: true },
      expect.anything(),
    )
    expect(screen.queryByTestId('approval-warnings')).not.toBeInTheDocument()
  })

  it('a plain Approve never sends approve_anyway', async () => {
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(setPhase).toHaveBeenCalledWith({ path: PATH, to: 'approved' }, expect.anything())
  })

  it("an incomplete refusal still lists its findings and offers no Approve anyway", async () => {
    setPhase.mockImplementationOnce((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(
        new ApiError(
          409,
          JSON.stringify({
            detail: {
              code: 'document_incomplete',
              message: 'cannot move to approved',
              blocking: [{ code: 'dependency_cycle', where: 'tasks', message: 'a -> b -> a' }],
              warnings: [skipped],
            },
          }),
        ),
      )
    })
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText(/a -> b -> a/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve anyway' })).not.toBeInTheDocument()
  })

  it("shows propose's warnings once the document is proposed", async () => {
    documents = [doc({ phase: 'exploring' })]
    propose.mockResolvedValue({ ...doc(), proposed: true, blocking: [], warnings: [skipped] })
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Propose' }))

    const list = await screen.findByTestId('approval-warnings')
    expect(within(list).getByTestId('approval-warning-steps_skipped')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve anyway' })).not.toBeInTheDocument()
  })

  it('an approved document shows the gaps its approval overrode, grouped the same way', () => {
    documents = [doc({ phase: 'approved', approval_warnings_overridden: [...criterionGaps, skipped] })]
    renderBar()

    const overridden = screen.getByTestId('approval-overridden')
    expect(
      within(overridden).getAllByTestId(/^approval-warning-/).map((line) => line.dataset.testid),
    ).toEqual(['approval-warning-requirement_without_criterion', 'approval-warning-steps_skipped'])
  })

  it('shows no overridden block for an approval that overrode nothing', () => {
    documents = [doc({ phase: 'approved', approval_warnings_overridden: [] })]
    renderBar()
    expect(screen.queryByTestId('approval-overridden')).not.toBeInTheDocument()
  })
})
