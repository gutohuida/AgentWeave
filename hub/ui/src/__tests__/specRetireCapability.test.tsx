import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'

/**
 * `a-capability-can-be-retired` (F536), the app half: a current capability offers Retire, which asks
 * for a reason and optionally the capability that absorbed it, sends both, and shows the Hub's
 * refusal; a retired capability says why and what absorbed it, and offers Retire no more.
 */
const setPhase = vi.fn()
let documents: unknown[] = []
let retired: unknown = undefined

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSpec: () => ({ data: { path: OLD, content: '', retired }, isError: false }),
    useCloseExploration: () => ({ mutate: vi.fn(), isPending: false }),
    useProposeSpecDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
    useSetSpecRigor: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSpecRigorHistory: () => ({ data: { events: [] }, error: null }),
    useDeleteSpecDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
  }
})

const OLD = 'spec/capabilities/old/spec.json'
const NEW = 'spec/capabilities/new/spec.json'

function capability(path: string, title: string, phase = 'current') {
  return {
    id: `spdoc-${title}`,
    path,
    title,
    kind: 'capability',
    phase,
    rigor: 'sketch',
    explore_closed: false,
    updated_at: '2026-10-08T00:00:00Z',
  }
}

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={OLD} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  documents = [capability(OLD, 'Old'), capability(NEW, 'New'), capability('spec/capabilities/gone/spec.json', 'Gone', 'archived')]
  retired = undefined
})

describe('retiring a capability', () => {
  it('offers Retire on a current capability and sends the reason and absorber', async () => {
    renderBar()
    await userEvent.click(screen.getByTestId('spec-retire-capability'))
    expect(screen.getByTestId('retire-confirm')).toBeDisabled()
    // Only other current capabilities can absorb it.
    const options = Array.from(screen.getByTestId('retire-absorbed-by').querySelectorAll('option')).map(
      (option) => option.textContent,
    )
    expect(options).toEqual(['No capability', 'New'])
    await userEvent.type(screen.getByTestId('retire-reason'), 'Never built.')
    await userEvent.selectOptions(screen.getByTestId('retire-absorbed-by'), NEW)
    await userEvent.click(screen.getByTestId('retire-confirm'))
    expect(setPhase).toHaveBeenCalledWith(
      { path: OLD, to: 'archived', reason: 'Never built.', absorbed_by: NEW },
      expect.anything(),
    )
  })

  it('sends no absorber when none is chosen', async () => {
    renderBar()
    await userEvent.click(screen.getByTestId('spec-retire-capability'))
    await userEvent.type(screen.getByTestId('retire-reason'), 'A sample.')
    await userEvent.click(screen.getByTestId('retire-confirm'))
    expect(setPhase).toHaveBeenCalledWith({ path: OLD, to: 'archived', reason: 'A sample.' }, expect.anything())
  })

  it('shows the Hub refusal in the dialog', async () => {
    setPhase.mockImplementation((_vars, options) =>
      options.onError(
        new ApiError(
          409,
          '{"detail":{"message":"open tasks still serve this capability","code":"capability_has_open_work"}}',
        ),
      ),
    )
    renderBar()
    await userEvent.click(screen.getByTestId('spec-retire-capability'))
    await userEvent.type(screen.getByTestId('retire-reason'), 'Gone.')
    await userEvent.click(screen.getByTestId('retire-confirm'))
    expect(screen.getByRole('alert')).toHaveTextContent('open tasks still serve this capability')
  })

  it('says why a retired capability left and what absorbed it, and offers Retire no more', () => {
    documents = [capability(OLD, 'Old', 'archived'), capability(NEW, 'New')]
    retired = { reason: 'Never built.', absorbed_by: NEW, at: '2026-10-08T12:00:00Z' }
    renderBar()
    expect(screen.queryByTestId('spec-retire-capability')).not.toBeInTheDocument()
    const note = screen.getByTestId('spec-retired-note')
    expect(note).toHaveTextContent('Never built.')
    expect(note).toHaveTextContent('Absorbed by New.')
  })
})
