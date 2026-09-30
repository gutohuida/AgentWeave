import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecProposalsPanel } from '@/components/spec/SpecProposalsPanel'

const acceptMutate = vi.fn()
const rejectMutate = vi.fn()
const withdrawMutate = vi.fn()
let proposals: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecProposals: () => ({ data: { proposals } }),
    useAcceptSpecProposal: () => ({ mutateAsync: acceptMutate, isPending: false }),
    useRejectSpecProposal: () => ({ mutateAsync: rejectMutate, isPending: false }),
    useWithdrawSpecProposal: () => ({ mutateAsync: withdrawMutate, isPending: false }),
  }
})

function renderPanel(path = 'spec/changes/demo/spec.html') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecProposalsPanel path={path} />
    </QueryClientProvider>,
  )
}

function proposal(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spprop-1',
    unit_kind: 'requirement',
    unit_key: 'alpha',
    change_kind: 'modify',
    position_after_key: null,
    proposed_payload: { statement: 'It responds within 100ms' },
    previous_payload: { statement: 'It responds within 200ms' },
    status: 'pending',
    proposer_actor_kind: 'agent',
    proposer_actor_name: 'claude-1',
    created_at: '2026-08-17T00:00:00Z',
    resolved_at: null,
    resolved_by_actor_name: null,
    resolution_reason: '',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  proposals = []
  acceptMutate.mockResolvedValue({})
  rejectMutate.mockResolvedValue({})
  withdrawMutate.mockResolvedValue({})
})

describe('SpecProposalsPanel', () => {
  it('renders nothing when there are no pending proposals', () => {
    const { container } = renderPanel()
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a pending proposal at its requirement key', () => {
    proposals = [proposal()]
    renderPanel()
    expect(screen.getByTestId('proposal-row-alpha')).toBeInTheDocument()
    expect(screen.getByText('It responds within 100ms')).toBeInTheDocument()
  })

  it('names the proposer', () => {
    proposals = [proposal({ proposer_actor_name: 'claude-1' })]
    renderPanel()
    expect(screen.getByText(/proposed by claude-1/)).toBeInTheDocument()
  })

  it('says where an add proposal will render', () => {
    proposals = [
      proposal({ unit_key: 'gamma', change_kind: 'add', position_after_key: 'beta' }),
    ]
    renderPanel()
    expect(screen.getByText(/after beta/)).toBeInTheDocument()
  })

  it('says an add proposal with no anchor renders at the top', () => {
    proposals = [proposal({ unit_key: 'gamma', change_kind: 'add', position_after_key: null })]
    renderPanel()
    expect(screen.getByText(/at the top/)).toBeInTheDocument()
  })

  it('accepts a proposal', async () => {
    proposals = [proposal()]
    renderPanel()

    await userEvent.click(screen.getByText('Accept'))

    expect(acceptMutate).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.html',
      proposalId: 'spprop-1',
    })
  })

  it('rejects a proposal after confirming, with a reason', async () => {
    proposals = [proposal()]
    renderPanel()

    await userEvent.click(screen.getByText('Reject'))
    await userEvent.type(screen.getByPlaceholderText('Reason (optional)'), 'not now')
    await userEvent.click(screen.getByText('Confirm reject'))

    expect(rejectMutate).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.html',
      proposalId: 'spprop-1',
      reason: 'not now',
    })
  })

  it('shows the metadata unit distinctly from a requirement', () => {
    proposals = [proposal({ unit_kind: 'metadata', unit_key: 'metadata', change_kind: 'modify' })]
    renderPanel()
    expect(screen.getByText('Summary / problem / scope')).toBeInTheDocument()
  })

  it('shows a refusal message on a failed accept', async () => {
    proposals = [proposal()]
    acceptMutate.mockRejectedValue(new Error('{"detail":{"message":"the document changed"}}'))
    renderPanel()

    await userEvent.click(screen.getByText('Accept'))

    await waitFor(() => {
      expect(screen.getByText('the document changed')).toBeInTheDocument()
    })
  })

  // `a-pending-proposal-can-be-withdrawn`, D4: a non-judgement exit, and twins marked. Fixtures are
  // in the order `GET …/proposals` returns them: `created_at` ascending.
  it('withdraws a proposal without judging it', async () => {
    proposals = [proposal()]
    renderPanel()

    await userEvent.click(screen.getByText('Withdraw'))

    expect(withdrawMutate).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.html',
      proposalId: 'spprop-1',
    })
    expect(rejectMutate).not.toHaveBeenCalled()
  })

  it('marks a repeat of an earlier pending proposal, and only the later one', () => {
    proposals = [
      proposal({ id: 'spprop-a', expected_digest: 'd1', created_at: '2026-09-30T10:00:00Z' }),
      proposal({
        id: 'spprop-b',
        unit_key: 'beta',
        proposed_payload: { statement: 'It logs the request' },
        expected_digest: 'd1',
        created_at: '2026-09-30T10:01:00Z',
      }),
      // Same content, keys in another order: still the same proposal (D4, R2).
      proposal({
        id: 'spprop-c',
        proposed_payload: { statement: 'It responds within 100ms' },
        previous_payload: { statement: 'It responds within 200ms' },
        expected_digest: 'd1',
        created_at: '2026-09-30T10:02:00Z',
      }),
    ]
    renderPanel()

    expect(screen.getAllByText('same as the one above')).toHaveLength(1)
    expect(screen.getByTestId('proposal-twin-spprop-c')).toHaveTextContent('same as the one above')
    expect(screen.queryByTestId('proposal-twin-spprop-a')).toBeNull()
  })

  it('marks the stale twin, not the live one, when the two were made against different versions', () => {
    proposals = [
      proposal({ id: 'spprop-old', expected_digest: 'd1', created_at: '2026-09-30T10:00:00Z' }),
      proposal({ id: 'spprop-new', expected_digest: 'd2', created_at: '2026-09-30T10:05:00Z' }),
    ]
    renderPanel()

    expect(screen.getByTestId('proposal-twin-spprop-old')).toHaveTextContent(
      'same as the one below, which was made against a newer version — this one would be refused as stale',
    )
    expect(screen.queryByTestId('proposal-twin-spprop-new')).toBeNull()
  })
})
