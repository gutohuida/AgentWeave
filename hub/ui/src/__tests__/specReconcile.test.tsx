import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { SpecDefectsReport } from '@/components/spec/SpecDefectsReport'

/**
 * `a-change-is-reconciled-with-its-code-before-it-is-folded`, the app half: the phase bar and the
 * fold dialog show the change's reconcile result (`fold_state.reconcile`, the shape `GET /spec`
 * answers, pinned by `test_the_fold_state_carries_the_latest_result_and_fold_is_not_refused`); a
 * change never reconciled offers Ask to reconcile; the rail counts each change's defects by step.
 */
const ask = vi.fn()
const record = vi.fn()
let foldState: unknown = undefined
let defects: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents: [doc()] } }),
    useSpec: () => ({ data: { path: CHANGE, content: '', fold_state: foldState }, isError: false }),
    useProposeSpecDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSetSpecPhase: () => ({ mutate: vi.fn(), isPending: false }),
    useSetSpecRigor: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSpecRigorHistory: () => ({ data: { events: [] }, error: null }),
    useFoldDraft: () => ({ data: undefined, isError: false }),
    useFoldDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useDeleteSpecDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useAskReconcile: () => ({ mutate: ask, isPending: false }),
    useSpecDefects: () => ({ data: { changes: defects }, error: null }),
    useRecordDefect: () => ({ mutate: record, isPending: false }),
    useProjectJourney: () => ({ data: { steps: [{ key: 'intake' }, { key: 'tasks' }], diagnostics: [] }, error: null }),
  }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: [{ name: 'rex', lifecycle: 'open' }], isError: false }) }
})

const CHANGE = 'spec/changes/service-routes/spec.json'

function doc() {
  return {
    id: 'spdoc-1',
    path: CHANGE,
    title: 'Service routes',
    kind: 'change-spec',
    phase: 'approved',
    rigor: 'sketch',
    explore_closed: true,
    updated_at: '2026-10-09T00:00:00Z',
  }
}

const RECONCILED = {
  state: 'recorded',
  id: 'spev-1',
  author: 'rex',
  run_id: 'run-1',
  at: '2026-10-09T09:00:00Z',
  summary: 'read app.py and curled every route',
  counts: { missing: 1, partial: 0, contradicts: 0, unrequested: 1 },
  gaps: [
    { class: 'missing', requirement: 'health', where: 'app.py', summary: 'no /health route' },
    { class: 'unrequested', requirement: null, where: '/debug', summary: 'dumps request headers' },
  ],
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  foldState = { state: 'ready', open_tasks: [], capabilities: [], reconcile: RECONCILED }
  defects = []
})

describe('reconcile before fold', () => {
  it('the phase bar says what reconciling found, in one line', () => {
    wrap(<SpecPhaseBar path={CHANGE} />)
    const line = screen.getByTestId('reconcile-result')
    expect(line).toHaveTextContent('@rex')
    expect(line).toHaveTextContent('1 missing · 1 unrequested')
    expect(line).not.toHaveTextContent('no /health route')
  })

  it('the fold dialog shows the counts and every gap', async () => {
    wrap(<SpecPhaseBar path={CHANGE} />)
    await userEvent.click(screen.getByTestId('fold-open'))

    const result = within(screen.getByRole('dialog')).getByTestId('reconcile-result')
    expect(result).toHaveTextContent('1 missing · 1 unrequested')
    expect(result).toHaveTextContent('no /health route')
    expect(result).toHaveTextContent('/debug')
  })

  it('a change never reconciled says so in the dialog and asks an agent to', async () => {
    foldState = { state: 'ready', open_tasks: [], capabilities: [], reconcile: { state: 'none' } }
    wrap(<SpecPhaseBar path={CHANGE} />)
    expect(screen.queryByTestId('reconcile-result')).not.toBeInTheDocument()
    await userEvent.click(screen.getByTestId('fold-open'))

    const none = within(screen.getByRole('dialog')).getByTestId('reconcile-none')
    await userEvent.selectOptions(within(none).getByLabelText('Agent to reconcile'), 'rex')
    await userEvent.click(within(none).getByTestId('reconcile-ask'))

    expect(ask).toHaveBeenCalledWith({ path: CHANGE, agent: 'rex' }, expect.anything())
  })
})

describe('defects by step', () => {
  it('lists each change with its count per step, and opens it', async () => {
    const onSelect = vi.fn()
    defects = [{
      document_id: 'spdoc-1', path: CHANGE, title: 'Service routes', phase: 'approved',
      defects: [], by_step: { reconcile: 1, review: 1, 'after-fold': 1 },
    }]
    wrap(<SpecDefectsReport onSelect={onSelect} />)

    const row = screen.getByTestId('spec-defects-row')
    expect(row).toHaveTextContent('Service routes')
    expect(row).toHaveTextContent('reconcile 1 · review 1 · after-fold 1')
    await userEvent.click(within(row).getByRole('button'))
    expect(onSelect).toHaveBeenCalledWith(CHANGE)
  })

  it('is absent while no change has a defect', () => {
    const { container } = wrap(<SpecDefectsReport onSelect={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('recording a defect', () => {
  it('records one against the open change with the step that caught it', async () => {
    wrap(<SpecDefectsReport currentPath={CHANGE} onSelect={vi.fn()} />)

    await userEvent.click(screen.getByTestId('spec-defect-add'))
    await userEvent.type(screen.getByLabelText('What went wrong'), '500 under load')
    await userEvent.selectOptions(screen.getByLabelText('Caught at'), 'review')
    await userEvent.click(screen.getByRole('button', { name: 'Record' }))

    expect(record).toHaveBeenCalledWith(
      { path: CHANGE, summary: '500 under load', caught_by: 'review' },
      expect.anything(),
    )
  })
})
