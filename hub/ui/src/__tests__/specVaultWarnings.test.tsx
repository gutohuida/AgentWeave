import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import { SpecVaultWarnings } from '@/components/spec/SpecVaultWarnings'

/**
 * A spec document's warnings from the vault (`a-requirement-is-checked-against-what-the-vault-
 * recorded`, FR-6). `GET /vault/warnings?path=` answers a cited fact's warnings first, then the
 * job's conflicts (`vault_spec_check.document_warnings`), and the fixtures here are in that order.
 * A 404 is a Hub that predates the route; it and an empty list both render nothing.
 */
const check = vi.fn()
let warnings: unknown[] | undefined = []
let warningsError: unknown = null

vi.mock('@/api/vault', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/vault')>()
  return {
    ...actual,
    useVaultWarnings: () => ({ data: warnings, error: warningsError }),
    useCheckVaultWarnings: () => ({ mutate: check, isPending: false }),
  }
})

const PATH = 'spec/changes/refunds/spec.json'

function warning(overrides: Record<string, unknown>) {
  return {
    key: 'small-refunds',
    identifier: 'FR-1',
    index: 0,
    statement: 'Refunds of 300 euros or less need no approval.',
    kind: 'disputed',
    fact: 'fct-1',
    message: 'Disputed: january-call says 300 euros, march-call says 500 euros.',
    ...overrides,
  }
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecVaultWarnings path={PATH} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  warningsError = null
  warnings = [
    warning({}),
    warning({
      key: 'large-refunds',
      identifier: 'FR-2',
      index: 1,
      statement: 'Refunds above 3,000 euros need approval.',
      kind: 'conflict',
      fact: 'fct-2',
      message: 'Contradicts fct-2: the limit is 300 euros.',
    }),
  ]
})

describe('SpecVaultWarnings', () => {
  it('lists each warning under its requirement, with the message naming both sources', () => {
    renderPanel()
    const first = screen.getByTestId('spec-vault-warning-small-refunds')
    expect(first).toHaveTextContent('FR-1')
    expect(first).toHaveTextContent('january-call')
    expect(first).toHaveTextContent('march-call')
    expect(screen.getByTestId('spec-vault-warning-large-refunds')).toHaveTextContent('FR-2')
    const rows = screen.getAllByTestId(/^spec-vault-warning-/)
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual([
      'spec-vault-warning-small-refunds',
      'spec-vault-warning-large-refunds',
    ])
  })

  it('renders nothing when the Hub has no route (404)', () => {
    warnings = undefined
    warningsError = new ApiError(404, 'Not Found')
    const { container } = renderPanel()
    expect(container).toBeEmptyDOMElement()
  })

  it('still offers Check now when the document has no warnings (F658)', () => {
    warnings = []
    renderPanel()
    expect(screen.getByText('No vault warnings')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('spec-vault-warnings-check'))
    expect(check).toHaveBeenCalledWith(PATH)
  })

  it('asks the Hub to check the document again, for this path', async () => {
    renderPanel()
    await userEvent.click(screen.getByTestId('spec-vault-warnings-check'))
    expect(check).toHaveBeenCalledTimes(1)
    expect(check.mock.calls[0][0]).toBe(PATH)
  })
})
