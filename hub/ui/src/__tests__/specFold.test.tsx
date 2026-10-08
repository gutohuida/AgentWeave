import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'

/**
 * `a-finished-change-is-folded-into-its-capability`, the app half: a shipped change in no
 * capability says so beside its phase, the fold dialog shows the Hub's draft and sends what the
 * operator edited, and archiving an unfolded change asks why it changes no capability.
 */
const setPhase = vi.fn()
const fold = vi.fn()
let documents: unknown[] = []
let foldState: unknown = undefined
let draft: unknown = undefined

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSpec: () => ({ data: { path: CHANGE, content: '', fold_state: foldState }, isError: false }),
    useCloseExploration: () => ({ mutate: vi.fn(), isPending: false }),
    useProposeSpecDocument: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSetSpecPhase: () => ({ mutate: setPhase, isPending: false }),
    useSetSpecRigor: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useSpecRigorHistory: () => ({ data: { events: [] }, error: null }),
    useFoldDraft: (_path: string, into: string | null) =>
      into ? { data: draft, isError: false } : { data: undefined, isError: false },
    useFoldDocument: () => ({ mutateAsync: fold, isPending: false }),
  }
})

const CHANGE = 'spec/changes/widgets-glow/spec.html'
const CAP = 'spec/capabilities/widgets/spec.html'

function doc(overrides: Record<string, unknown> = {}) {
  return {
    id: 'spdoc-1',
    path: CHANGE,
    title: 'Widgets glow',
    kind: 'change-spec',
    phase: 'approved',
    rigor: 'sketch',
    explore_closed: true,
    updated_at: '2026-10-08T00:00:00Z',
    ...overrides,
  }
}

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecPhaseBar path={CHANGE} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  fold.mockResolvedValue({ ...doc({ phase: 'archived' }), archived: true, merged: 1 })
  documents = [
    doc(),
    { ...doc({ id: 'spdoc-cap', path: CAP, title: 'Widgets', kind: 'capability', phase: 'current' }) },
  ]
  foldState = { state: 'ready', open_tasks: [], capabilities: [] }
  draft = {
    into: CAP,
    requirements: [
      { from: 'glow', key: 'widgets-glow-glow', statement: 'A widget MUST glow.', modal: 'MUST', replaces: null },
      { from: 'dim', key: 'widgets-glow-dim', statement: 'A widget SHOULD dim.', modal: 'SHOULD', replaces: null },
    ],
    collisions: [],
  }
})

describe('folding a finished change', () => {
  it('says a ready change is shipped but in no capability, and offers the fold', () => {
    renderBar()
    expect(screen.getByTestId('fold-state')).toHaveAttribute('data-state', 'ready')
    expect(screen.getByTestId('fold-open')).toBeInTheDocument()
  })

  it('offers no fold while a task is still open', () => {
    foldState = { state: 'tasks_open', open_tasks: ['task-1'], capabilities: [] }
    renderBar()
    expect(screen.queryByTestId('fold-open')).not.toBeInTheDocument()
  })

  it('names the capability a folded change went into', () => {
    foldState = { state: 'folded', open_tasks: [], capabilities: [CAP] }
    renderBar()
    expect(screen.getByTestId('fold-state')).toHaveTextContent(CAP)
  })

  it('folds the draft with the operator’s edits and archives by default', async () => {
    renderBar()
    await userEvent.click(screen.getByTestId('fold-open'))
    await userEvent.selectOptions(screen.getByTestId('fold-capability'), CAP)

    expect(screen.getByTestId('fold-req-key-glow')).toHaveValue('widgets-glow-glow')
    const statement = screen.getByTestId('fold-req-statement-glow')
    await userEvent.clear(statement)
    await userEvent.type(statement, 'A widget MUST glow while hovered.')
    await userEvent.click(screen.getByTestId('fold-req-include-dim'))
    await userEvent.click(screen.getByTestId('fold-confirm'))

    await waitFor(() => expect(fold).toHaveBeenCalledTimes(1))
    expect(fold).toHaveBeenCalledWith({
      path: CHANGE,
      into: CAP,
      archive: true,
      requirements: [
        { key: 'glow', as_key: 'widgets-glow-glow', statement: 'A widget MUST glow while hovered.' },
      ],
    })
  })

  it('holds the confirm while a kept key collides, until it is renamed', async () => {
    draft = { ...(draft as object), collisions: ['widgets-glow-dim'] }
    renderBar()
    await userEvent.click(screen.getByTestId('fold-open'))
    await userEvent.selectOptions(screen.getByTestId('fold-capability'), CAP)

    expect(screen.getByTestId('fold-req-collision-dim')).toBeInTheDocument()
    expect(screen.getByTestId('fold-confirm')).toBeDisabled()
    const key = screen.getByTestId('fold-req-key-dim')
    await userEvent.clear(key)
    await userEvent.type(key, 'widgets-dim-when-idle')
    expect(screen.getByTestId('fold-confirm')).toBeEnabled()
  })

  it('shows the Hub’s refusal in the dialog', async () => {
    fold.mockRejectedValue(
      new ApiError(
        409,
        JSON.stringify({ detail: { message: 'this change still has open tasks', code: 'fold_tasks_open' } }),
      ),
    )
    renderBar()
    await userEvent.click(screen.getByTestId('fold-open'))
    await userEvent.selectOptions(screen.getByTestId('fold-capability'), CAP)
    await userEvent.click(screen.getByTestId('fold-confirm'))

    expect(await screen.findByTestId('fold-error')).toHaveTextContent(/open tasks/)
  })

  it('asks why an unfolded change changes no capability before archiving it', async () => {
    renderBar()
    await userEvent.click(screen.getByText('Archive'))

    expect(screen.getByTestId('archive-confirm')).toBeDisabled()
    await userEvent.type(screen.getByTestId('archive-reason'), 'it only retired a finding')
    await userEvent.click(screen.getByTestId('archive-confirm'))

    expect(setPhase).toHaveBeenCalledWith(
      { path: CHANGE, to: 'archived', reason: 'it only retired a finding', no_capability_change: true },
      expect.anything(),
    )
  })

  it('archives a folded change without asking', async () => {
    foldState = { state: 'folded', open_tasks: [], capabilities: [CAP] }
    renderBar()
    await userEvent.click(screen.getByText('Archive'))

    expect(screen.queryByTestId('archive-reason')).not.toBeInTheDocument()
    await userEvent.click(screen.getByTestId('archive-confirm'))
    expect(setPhase).toHaveBeenCalledWith({ path: CHANGE, to: 'archived' }, expect.anything())
  })
})
