import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { useSpecPhaseControls } from '@/components/spec/useSpecPhaseControls'
import { ApiError } from '@/api/client'

/**
 * Acknowledged gaps in Check and Approve (`ready-means-the-same-thing`, FR-5, FR-6, FR-11).
 * Approval lists what is missing and can approve anyway (`approve-lists-what-is-missing-and-can-
 * approve-anyway`, FR-7). The 409 is the shape `POST /documents/phase` answers
 * (`hub/tests/test_approval_warnings_routes.py`): `{detail: {code: 'approval_warnings', message,
 * warnings: [{code, where, message}]}}`, the gaps in the order `phase_findings` lists them — the
 * completeness findings first, `steps_skipped` last.
 */
const check = vi.fn()
const setPhase = vi.fn()
const approveAndBuild = vi.fn()
const acknowledge = vi.fn()
let documents: unknown[] = []
// What `GET /spec` read the document with: the acknowledged gaps, before any Check.
let loadedAcknowledged: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSetSpecJourney: () => ({ mutate: vi.fn(), isPending: false }),
    useSpec: () => ({
      data: { path: PATH, content: '', content_version: 'v1', acknowledged: loadedAcknowledged },
      isError: false,
      refetch: vi.fn(),
    }),
    useCheckSpecDocument: () => ({ mutateAsync: check, isPending: false }),
    useAcknowledgeSpecGap: () => ({ mutateAsync: acknowledge, isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
    useApproveAndBuildSpecDocument: () => ({ mutate: approveAndBuild, isPending: false }),
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
    phase: 'exploring',
    rigor: 'contract',
    content_digest: null,
    explore_closed: true,
    updated_at: '2026-10-09T00:00:00Z',
    ...overrides,
  }
}

const open = {
  code: 'criterion_without_check',
  where: 'requirements.a.criteria.c1',
  message: 'criterion c1 names no way to check it',
}
const acked = {
  code: 'no_acceptance_drive',
  where: 'tasks',
  message: 'no drive task',
  reason: 'the drive is a follow-up slice',
  by: 'operator',
  by_kind: 'operator',
  at: '2026-11-16T10:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  setPhase.mockReset()
  documents = [doc()]
  loadedAcknowledged = []
})

/** The spec page's mode: Check's findings are drawn inline (`useSpecSurface`), not in the header. */
function InlineHarness() {
  const controls = useSpecPhaseControls(PATH, undefined, undefined, { inlineFindings: true })
  if (!controls) return null
  return (
    <div>
      <button onClick={controls.actions.check}>Check</button>
      {controls.messages}
    </div>
  )
}

describe('acknowledged gaps', () => {
  it('on the page (inline findings) Check offers Acknowledge for a gap, never for a note', async () => {
    const note = { code: 'recommended_people', where: 'tasks', message: 'Task docs names no builder' }
    check.mockResolvedValueOnce({ blocking: [], warnings: [open, note], acknowledged: [], ready: false })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <InlineHarness />
      </QueryClientProvider>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))
    const controls = await screen.findAllByTestId('acknowledge-open')
    expect(controls).toHaveLength(1)
    expect(controls[0]).not.toHaveTextContent(/builder/i)
  })


  it('the page shows an acknowledged gap on load, with no Check', () => {
    loadedAcknowledged = [acked]
    renderBar()
    const list = screen.getByTestId('acknowledged-gaps-list')
    expect(list).toHaveTextContent('Acknowledged by operator')
    expect(list).toHaveTextContent('the drive is a follow-up slice')
    expect(check).not.toHaveBeenCalled()
  })

  it('Check shows an acknowledged gap with reason and author apart from the open one', async () => {
    check.mockResolvedValueOnce({ blocking: [], warnings: [open], acknowledged: [acked], ready: false })
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))

    const list = await screen.findByTestId('acknowledged-gaps-list')
    expect(within(list).getByTestId('acknowledged-gap-no_acceptance_drive')).toHaveTextContent(
      'Acknowledged by operator',
    )
    expect(list).toHaveTextContent('the drive is a follow-up slice')
    const open_ = screen.getByTestId('approval-warnings')
    expect(within(open_).getByTestId('approval-warning-criterion_without_check')).toBeInTheDocument()
    expect(within(open_).queryByTestId('approval-warning-no_acceptance_drive')).not.toBeInTheDocument()
    expect(list).not.toContainElement(open_)
  })

  it('the operator acknowledges an open gap from Check, and the verdict updates', async () => {
    check.mockResolvedValueOnce({ blocking: [], warnings: [open], acknowledged: [], ready: false })
    acknowledge.mockResolvedValueOnce({
      blocking: [],
      warnings: [],
      acknowledged: [{ ...open, reason: 'covered by the drive', by: 'operator', at: '2026-11-16T10:05:00Z' }],
      ready: true,
    })
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))
    await userEvent.click(await screen.findByTestId('acknowledge-open'))
    const submit = screen.getByTestId('acknowledge-submit')
    // No reason, no acknowledgement.
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByTestId('acknowledge-reason'), 'covered by the drive')
    await userEvent.click(submit)

    expect(acknowledge).toHaveBeenCalledWith({
      path: PATH,
      code: open.code,
      where: open.where,
      reason: 'covered by the drive',
    })
    const list = await screen.findByTestId('acknowledged-gaps-list')
    expect(list).toHaveTextContent('covered by the drive')
    expect(screen.queryByTestId('approval-warnings')).not.toBeInTheDocument()
    expect(screen.getByTestId('spec-check-clean')).toBeInTheDocument()
  })

  it('a refused acknowledgement says why and leaves the gap open', async () => {
    check.mockResolvedValueOnce({ blocking: [], warnings: [open], acknowledged: [], ready: false })
    acknowledge.mockRejectedValueOnce(new ApiError(422, 'a reason is required'))
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Check' }))
    await userEvent.click(await screen.findByTestId('acknowledge-open'))
    await userEvent.type(screen.getByTestId('acknowledge-reason'), 'x')
    await userEvent.click(screen.getByTestId('acknowledge-submit'))
    expect(await screen.findByTestId('acknowledge-refusal')).toBeInTheDocument()
    expect(screen.getByTestId('approval-warnings')).toBeInTheDocument()
  })

  it('approving over acknowledged gaps does not stop and lists them', async () => {
    setPhase.mockImplementationOnce((_vars: unknown, options: { onSuccess: (r: unknown) => void }) => {
      options.onSuccess({ ...doc({ phase: 'approved' }), acknowledged: [acked] })
    })
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    expect(screen.queryByTestId('spec-approve-anyway')).not.toBeInTheDocument()
    expect(setPhase).toHaveBeenCalledTimes(1)
    const list = await screen.findByTestId('acknowledged-gaps-list')
    expect(list).toHaveTextContent('Acknowledged by operator')
  })
})
