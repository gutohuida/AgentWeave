import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'

/**
 * The controls an operator has and an agent does not.
 *
 * `importOriginal` is used so this file does not join the nine that replace a
 * whole api module with a bare object — a partial mock keeps the rest of the
 * module's exports real, so a rename elsewhere fails loudly here.
 */
const closeExploration = vi.fn()
const propose = vi.fn()
const setPhase = vi.fn()
let documents: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useCloseExploration: () => ({ mutate: closeExploration, isPending: false }),
    useProposeSpecDocument: () => ({ mutateAsync: propose, isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
  }
})

function renderBar(path = 'spec/changes/demo/spec.html') {
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
    path: 'spec/changes/demo/spec.html',
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

  it('offers closing exploration while exploring, and not proposing yet', () => {
    renderBar()
    expect(screen.getByText('Exploration is complete')).toBeInTheDocument()
    expect(screen.queryByText('Propose')).not.toBeInTheDocument()
  })

  it('offers proposing only once exploration has been closed', () => {
    documents = [doc({ explore_closed: true })]
    renderBar()
    expect(screen.getByText('Propose')).toBeInTheDocument()
    expect(screen.queryByText('Exploration is complete')).not.toBeInTheDocument()
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

    expect(setPhase).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.html',
      to: 'approved',
    })
  })

  it('can reopen an approved document', async () => {
    documents = [doc({ phase: 'approved', explore_closed: true })]
    renderBar()

    await userEvent.click(screen.getByText('Reopen'))

    expect(setPhase).toHaveBeenCalledWith({
      path: 'spec/changes/demo/spec.html',
      to: 'exploring',
    })
  })

  it('does not offer reopening a document that is already exploring', () => {
    renderBar()
    expect(screen.queryByText('Reopen')).not.toBeInTheDocument()
  })
})
