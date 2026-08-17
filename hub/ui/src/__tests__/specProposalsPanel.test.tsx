import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecProposalsPanel } from '@/components/spec/SpecProposalsPanel'

const acceptMutate = vi.fn()
const rejectMutate = vi.fn()
let proposals: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecProposals: () => ({ data: { proposals } }),
    useAcceptSpecProposal: () => ({ mutateAsync: acceptMutate, isPending: false }),
    useRejectSpecProposal: () => ({ mutateAsync: rejectMutate, isPending: false }),
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
})
