import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SpecPhaseBar } from '@/components/spec/SpecPhaseBar'
import { ApiError } from '@/api/client'
import { GapLines } from '@/components/spec/SpecPhaseParts'

/**
 * Approval lists what is missing and can approve anyway (`approve-lists-what-is-missing-and-can-
 * approve-anyway`, FR-7). The 409 is the shape `POST /documents/phase` answers
 * (`hub/tests/test_approval_warnings_routes.py`): `{detail: {code: 'approval_warnings', message,
 * warnings: [{code, where, message}]}}`, the gaps in the order `phase_findings` lists them — the
 * completeness findings first, `steps_skipped` last.
 */
const check = vi.fn()
const setPhase = vi.fn()
const approveAndBuild = vi.fn()
let documents: unknown[] = []

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents } }),
    useSetSpecJourney: () => ({ mutate: vi.fn(), isPending: false }),
    useSpec: () => ({ data: { path: PATH, content: '', content_version: 'v1' }, isError: false, refetch: vi.fn() }),
    useCheckSpecDocument: () => ({ mutateAsync: check, isPending: false }),
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

// vitest stubs css imports to '', and the UI has no node typings: read the file the way node does.
// @ts-expect-error no node typings in the UI project
const { readFileSync } = (await import('node:fs')) as { readFileSync: (p: string, enc: string) => string }
const specHeaderCss = readFileSync('src/styles/spec-header.css', 'utf8')

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
    expect(lines[0]).toHaveTextContent('5 requirements have no acceptance criterion')
    expect(lines[1]).toHaveTextContent('This spec skipped steps')
    // AW-127: plain words — no snake_case code, no route.
    expect(list.textContent).not.toMatch(/[a-z]+_[a-z_]+/)
    expect(list.textContent).not.toMatch(/\/api\//)
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
      { path: PATH, to: 'approved', content_version: 'v1', approve_anyway: true },
      expect.anything(),
    )
    expect(screen.queryByTestId('approval-warnings')).not.toBeInTheDocument()
  })

  it('Approve and build is refused like approving, and its Approve anyway resends it', async () => {
    approveAndBuild.mockImplementationOnce((_vars: unknown, options: { onError: (e: unknown) => void }) => {
      options.onError(
        new ApiError(
          409,
          JSON.stringify({
            detail: { code: 'approval_warnings', message: 'gaps', warnings: [skipped] },
          }),
        ),
      )
    })
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve and build…' }))
    // No recommendation to fill in: confirming approves and builds with the settings the dialog
    // showed, by hand at Reviewed (`a-build-has-a-driver-a-level-and-its-people`).
    await userEvent.click(await screen.findByTestId('build-confirm'))
    const shown = {
      driver: 'hand',
      level: 'reviewed',
      builder: '',
      checker: '',
      builders: [],
      landing: 'main',
      task_builders: {},
      task_checkers: {},
    }
    expect(approveAndBuild).toHaveBeenLastCalledWith(
      { path: PATH, content_version: 'v1', ...shown },
      expect.anything(),
    )
    await screen.findByTestId('approval-warnings')

    await userEvent.click(screen.getByRole('button', { name: 'Approve and build anyway' }))

    expect(approveAndBuild).toHaveBeenLastCalledWith(
      { path: PATH, content_version: 'v1', approve_anyway: true, ...shown },
      expect.anything(),
    )
    expect(setPhase).not.toHaveBeenCalled()
  })

  it('a plain Approve never sends approve_anyway', async () => {
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(setPhase).toHaveBeenCalledWith(
      { path: PATH, to: 'approved', content_version: 'v1' },
      expect.anything(),
    )
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

  it("shows Check's warnings, and Check offers no Approve anyway", async () => {
    check.mockResolvedValue({ ...doc(), ready: true, blocking: [], warnings: [skipped] })
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: 'Check' }))

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

  it('names every finding whose message differs, so both same-file pairs reach the screen (F1015)', () => {
    const overlaps = [
      { code: 'unordered_file_overlap', where: 'tasks', message: "tasks 't1' and 't2' both edit 'lib.py' without depends_on" },
      { code: 'unordered_file_overlap', where: 'tasks', message: "tasks 't3' and 't4' both edit 'util.py' without depends_on" },
    ]
    render(<GapLines gaps={overlaps} />)
    expect(screen.getByText(/lib\.py/)).toBeInTheDocument()
    expect(screen.getByText(/util\.py/)).toBeInTheDocument()
  })

  it('shows no overridden block for an approval that overrode nothing', () => {
    documents = [doc({ phase: 'approved', approval_warnings_overridden: [] })]
    renderBar()
    expect(screen.queryByTestId('approval-overridden')).not.toBeInTheDocument()
  })

  it('F1128: Approve anyway comes after the warning text and list, in a stacked block', async () => {
    refuseWithGaps()
    renderBar()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))

    const block = await screen.findByTestId('approval-warnings')
    const button = within(block).getByTestId('spec-approve-anyway')
    const list = block.querySelector('ul') as HTMLElement
    // Fails before the fix: the button sat between the text and the list, in a wrapping row.
    expect(list.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(block).toHaveAttribute('data-stack', 'true')
  })

  it('F1128: the stacked block lays out as a column and scrolls its list', () => {
    // jsdom has no layout: the rule that keeps the button below the text is asserted in the sheet.
    const rule = specHeaderCss.match(/\.aw-spec-message\[data-stack="true"\]\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(rule).toContain('flex-direction: column')
    expect(rule).toContain('flex-wrap: nowrap')
    expect(specHeaderCss).toMatch(/\[data-stack="true"\]\s*>\s*ul\s*\{[^}]*overflow-y:\s*auto/)
  })
})

describe('plainGap recommended_people', () => {
  const gap = (message: string) => [{ code: 'recommended_people', where: 'tasks', message }]
  it('says a same-agent builder and checker is an error, not "no builder"', () => {
    render(<GapLines gaps={gap("task 't1' has 'Dev' as both builder and checker, which cannot be carried out")} />)
    const line = screen.getByTestId('approval-warning-recommended_people')
    expect(line).toHaveTextContent('Task t1 names Dev as both builder and checker')
    expect(line).not.toHaveTextContent('No builder or checker')
  })
  it('keeps each problem apart', () => {
    render(<GapLines gaps={gap("task 't2' has no recommended builder; a checker with no reason")} />)
    expect(screen.getByTestId('approval-warning-recommended_people')).toHaveTextContent(
      'Task t2 names no builder, and names a checker without saying why.',
    )
  })
})

describe('Check findings are plain words too (AW-127)', () => {
  it('the inline finding the Spec page shows has no code, no route and no snake_case field', async () => {
    const { findingsOf } = await import('@/components/spec/page/adapt')
    const hubSaid = [
      {
        code: 'steps_skipped',
        where: 'step',
        message:
          "the document is at step 'intake'; this project's journey (size small) goes on to requirements-and-acceptance, tasks, build, which it never reached. If it already holds what those steps produce, record that: POST /api/v1/projects/p/project/documents/journey?path=x {\"step\": \"build\"} (the step control on its phase bar)",
      },
      { code: 'criterion_without_check', where: 'acceptance_criteria[0]', message: "'ac-1' has no how_to_check and no checked_by, so nobody is named to check it or how" },
    ]
    const found = findingsOf([], hubSaid, { requirements: [], tasks: [] } as never, null)
    for (const f of found) {
      expect(f.message).not.toMatch(/\/api\//)
      expect(f.message).not.toMatch(/[a-z]+_[a-z_]+/)
    }
    expect(found[0].message).toContain('requirements-and-acceptance → tasks → build')
    expect(found[1].message).toContain('ac-1')
  })
})
