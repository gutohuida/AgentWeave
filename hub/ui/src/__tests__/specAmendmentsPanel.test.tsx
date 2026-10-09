import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecAmendmentsPanel } from '@/components/spec/SpecAmendmentsPanel'

/**
 * A tester's amendments to an approved document (`a-tester-drives-the-built-product-and-keeps-the-
 * spec-true`, FR-9). `GET /documents/{path}/amendments` answers oldest first
 * (`spec_amendments.list_amendments` orders by `created_at, id`; pinned by
 * `test_the_operator_marks_reviewed_per_item_then_for_the_document`), and every fixture here is in
 * that order.
 */
const review = vi.fn()
let amendments: unknown[] = []
let documents: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSpecAmendments: () => ({ data: { amendments }, error: null }),
    useReviewSpecAmendments: () => ({ mutate: review, isPending: false }),
  }
})

const PATH = 'spec/changes/demo/spec.json'

function amendment(overrides: Record<string, unknown>) {
  return {
    id: 'amd-1',
    op: 'add_task',
    target: 'fix-negative',
    requirement: 'adds',
    identifier: 'FR-1',
    reason: 'ran python calc.py -2 3: printed 5',
    how_to_check: 'python calc.py -2 3',
    author: 'tess',
    run_id: 'run-abc',
    created_at: '2026-10-09T09:00:00Z',
    reviewed: false,
    reviewed_at: null,
    reviewed_by: null,
    relaxing: false,
    change: null,
    before: null,
    ...overrides,
  }
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecAmendmentsPanel path={PATH} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  documents = [{ id: 'spdoc-1', path: PATH, phase: 'approved', amendments: { total: 2, unreviewed: 1 } }]
  amendments = [
    amendment({ id: 'amd-1', reviewed: true, reviewed_by: 'operator', reviewed_at: '2026-10-09T09:05:00Z' }),
    amendment({
      id: 'amd-2',
      op: 'change_criterion',
      target: 'negative',
      relaxing: true,
      reason: 'the criterion was too strict',
      run_id: 'run-def',
    }),
  ]
})

describe('SpecAmendmentsPanel', () => {
  it('lists each amendment with author, run, reason and how to check, oldest first', () => {
    renderPanel()

    const rows = screen.getAllByTestId(/^spec-amendment-amd-/)
    expect(rows.map((row) => row.dataset.testid)).toEqual(['spec-amendment-amd-1', 'spec-amendment-amd-2'])
    expect(rows[0]).toHaveTextContent('tess')
    expect(rows[0]).toHaveTextContent('run-abc')
    expect(rows[0]).toHaveTextContent('printed 5')
    expect(rows[0]).toHaveTextContent('python calc.py -2 3')
    expect(rows[0]).toHaveTextContent(/reviewed/i)
  })

  it('offers Mark reviewed only on the one not reviewed, and sends its id', async () => {
    renderPanel()

    const rows = screen.getAllByTestId(/^spec-amendment-amd-/)
    expect(within(rows[0]).queryByRole('button', { name: 'Mark reviewed' })).not.toBeInTheDocument()
    await userEvent.click(within(rows[1]).getByRole('button', { name: 'Mark reviewed' }))

    expect(review).toHaveBeenCalledWith({ path: PATH, ids: ['amd-2'] })
  })

  it('says a relaxing amendment holds its requirement back until reviewed', () => {
    renderPanel()

    expect(screen.getByTestId('spec-amendment-amd-2')).toHaveTextContent(/FR-1.*cannot be verified/)
  })

  it('marks every amendment reviewed for the document', async () => {
    renderPanel()

    await userEvent.click(screen.getByRole('button', { name: 'Mark all reviewed' }))

    expect(review).toHaveBeenCalledWith({ path: PATH })
  })

  it('renders nothing for a document with no amendments', () => {
    documents = [{ id: 'spdoc-1', path: PATH, phase: 'approved' }]
    amendments = []
    const { container } = renderPanel()
    expect(container).toBeEmptyDOMElement()
  })
})
