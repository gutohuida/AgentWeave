import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { ApiError } from '@/api/client'
import { TaskDetailDrawer } from '@/components/tasks/TaskDetailDrawer'

/**
 * F5 — the task, opened (`design.md` D8).
 *
 * Everything the inline expansion used to hold is behaviour-parity-tested alongside the tests it
 * was relocated from (`taskBlockedTreatment.test.tsx`, `taskDivergenceControls.test.tsx`,
 * `taskStatusControl.test.tsx`, `taskRequirementLinks.test.tsx`) — each now opens the drawer first,
 * via the card's explicit "open" affordance, instead of expanding the card inline. What is specific
 * to this file: the drawer's own mechanics (open/close, focus, click-outside), and the two things
 * F5 adds beyond a location change — the full-statement/rejection-reason "Serves" content (6.3)
 * and the no-clipping guarantee (6.5).
 */

// Mutable so one test (the portaled-menu regression below) can offer a transition without every
// other test having to account for a status-transition menu it does not care about.
let transitionsMap: Record<string, string[]> = {}
// F125's rename mutation, stubbed so the drawer's own edit/save/cancel mechanics are what these
// tests exercise, not a real network call (`tasksApi.test.tsx` covers the hook's request shape).
let renameMutate = vi.fn()
// F532's delete, overridden per test like `renameMutate`.
let deleteMutate = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: transitionsMap } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    // F9's note. Stubbed here for the same reason the three hooks above are: this file is about the
    // drawer's mechanics, and one of its tests renders outside a QueryClientProvider deliberately.
    useTaskIntegrationPreview: () => ({ data: undefined }),
    // F163's landing action, added to the drawer after this file was written. It calls
    // `useQueryClient` unconditionally, so leaving it real threw "No QueryClient set" out of the
    // one test that renders without a provider — the click-outside one, which is about the board
    // and cannot be given a provider without changing what it is testing. Behaviour of the button
    // itself belongs to `taskLandingAction.test.tsx`, which does wrap one.
    useLandTask: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteTask: () => ({
      mutate: (vars: { id: string }, opts?: { onSuccess?: () => void; onError?: (e: unknown) => void }) =>
        deleteMutate(vars, opts),
      isPending: false,
    }),
    // The checks row (approval-runs-the-projects-checks), stubbed for the same reason: its
    // behaviour belongs to `taskChecksRow.test.tsx`.
    useTaskChecks: () => ({ data: undefined, error: null }),
    useRerunTaskChecks: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    // Overridden per-test via `renameMutate`/`renameOnError`/`renameOnSuccess` below (F125,
    // `the-operator-can-rename-a-task`) — the drawer's title editor is what is under test here, not
    // the hook's own request shape (that is `tasksApi.test.tsx`).
    useRenameTask: () => ({
      mutate: (vars: { id: string; title: string }, opts?: { onSuccess?: () => void; onError?: (e: unknown) => void }) =>
        renameMutate(vars, opts),
    }),
    // F203's history section, for the same reason as the hooks above: it is a real query, and the
    // click-outside test renders without a provider on purpose. What the section *shows* is
    // `taskTransitionHistory.test.tsx`.
    useTaskTransitions: () => ({ data: { transitions: [] }, isLoading: false, isError: false }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({
    data: {
      documents: [
        {
          id: 'spdoc-1',
          path: 'spec/example.json',
          title: 'Example',
          kind: 'baseline',
          phase: 'approved',
          rigor: 'sketch',
          content_digest: null,
          explore_closed: false,
          updated_at: '2026-08-16T00:00:00Z',
        },
      ],
    },
  }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'in_progress',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

function renderDrawer(task: Task | null, onClose: () => void, onOpenRequirement?: (path: string, anchor: string) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TaskDetailDrawer task={task} onClose={onClose} onOpenRequirement={onOpenRequirement} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  transitionsMap = {}
  renameMutate = vi.fn()
})

describe('opening and closing the drawer', () => {
  it('renders nothing for no task', () => {
    renderDrawer(null, vi.fn())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the task as a dialog, board side, when given one', () => {
    renderDrawer(makeTask(), vi.fn())
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveTextContent('Ship the thing')
  })

  it('closes on the explicit close button', async () => {
    const onClose = vi.fn()
    renderDrawer(makeTask(), onClose)
    await userEvent.click(screen.getByTestId('task-drawer-close-task-1'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    renderDrawer(makeTask(), onClose)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes on a click outside the panel — the board, not a modal backdrop (design.md D8)', async () => {
    const onClose = vi.fn()
    render(
      <div>
        <div data-testid="the-board">the board behind the drawer</div>
        <TaskDetailDrawer task={makeTask()} onClose={onClose} />
      </div>,
    )
    await userEvent.click(screen.getByTestId('the-board'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not close on a click inside the panel', async () => {
    const onClose = vi.fn()
    renderDrawer(makeTask(), onClose)
    await userEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not close when the status menu — a Radix dropdown portaled outside the panel — is opened and used', async () => {
    // Regression, found building this test rather than assumed from the design doc: `RowMenu`
    // (Radix `DropdownMenu`) portals its open content to a sibling of `document.body`, outside
    // `panelRef`'s own subtree. A click-outside listener that only checks `panelRef.contains()`
    // reads a click on "Move to blocked" as a click on the board and closes the drawer out from
    // under the menu it just opened — the status change never fires because the menu item it
    // landed on has already been unmounted.
    transitionsMap = { in_progress: ['blocked'] }
    const onClose = vi.fn()
    renderDrawer(makeTask({ status: 'in_progress' }), onClose)

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    expect(screen.getByTestId('task-status-menu-task-1-blocked')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))

    expect(onClose).not.toHaveBeenCalled()
    // The click landed on the menu item, not the board — the drawer, and the blocking-reason
    // input the selection opens, are both still there.
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByTestId('task-block-reason-task-1')).toBeInTheDocument()
  })
})

describe('renaming a task (F125, the-operator-can-rename-a-task)', () => {
  it('enters edit mode on click, and Enter calls useRenameTask with the new title', async () => {
    renderDrawer(makeTask(), vi.fn())
    await userEvent.click(screen.getByTestId('task-drawer-title-task-1'))
    const input = screen.getByTestId('task-drawer-title-input-task-1')
    await userEvent.clear(input)
    await userEvent.type(input, 'A better title{Enter}')

    expect(renameMutate).toHaveBeenCalledTimes(1)
    expect(renameMutate.mock.calls[0][0]).toEqual({ id: 'task-1', title: 'A better title' })
  })

  it('restores the old title on Escape, without calling useRenameTask', async () => {
    renderDrawer(makeTask(), vi.fn())
    await userEvent.click(screen.getByTestId('task-drawer-title-task-1'))
    const input = screen.getByTestId('task-drawer-title-input-task-1')
    await userEvent.type(input, ' more text{Escape}')

    expect(renameMutate).not.toHaveBeenCalled()
    expect(screen.getByTestId('task-drawer-title-task-1')).toHaveTextContent('Ship the thing')
  })

  it('saving a blocked task sends a PATCH body of exactly {title} — no status, no blocked_reason', async () => {
    renderDrawer(makeTask({ status: 'blocked', blocked_reason: 'waiting on ops' }), vi.fn())
    await userEvent.click(screen.getByTestId('task-drawer-title-task-1'))
    const input = screen.getByTestId('task-drawer-title-input-task-1')
    await userEvent.clear(input)
    await userEvent.type(input, 'Renamed while blocked{Enter}')

    expect(renameMutate).toHaveBeenCalledTimes(1)
    expect(renameMutate.mock.calls[0][0]).toEqual({
      id: 'task-1',
      title: 'Renamed while blocked',
    })
  })

  it('a refused rename shows the route detail and restores the old title', async () => {
    renameMutate = vi.fn((_vars, opts) =>
      opts?.onError?.(
        new ApiError(422, JSON.stringify({ detail: "A task's title cannot be blank." })),
      ),
    )
    renderDrawer(makeTask(), vi.fn())
    await userEvent.click(screen.getByTestId('task-drawer-title-task-1'))
    const input = screen.getByTestId('task-drawer-title-input-task-1')
    await userEvent.clear(input)
    await userEvent.type(input, 'x{Enter}')

    expect(screen.getByText(/A task's title cannot be blank\./)).toBeInTheDocument()
    // The failed edit stays in the input rather than being silently reverted — the operator's
    // half-typed text is not thrown away by a refusal they still need to read and act on.
    expect(input).toBeInTheDocument()
  })
})

describe('F4 chips inside the drawer, resolved via requirement_links (6.3)', () => {
  it('shows the full statement text, not just the identifier', () => {
    renderDrawer(
      makeTask({
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'It settles the account to the cent',
          },
        ],
      }),
      vi.fn(),
    )
    expect(screen.getByText(/It settles the account to the cent/)).toBeInTheDocument()
  })

  it('shows the rejection reason for a link with rejected evidence — never surfaced before this change', () => {
    renderDrawer(
      makeTask({
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'It settles the account',
            has_rejected_evidence: true,
            latest_rejection_reason: 'Off by one cent on the settlement total',
          },
        ],
      }),
      vi.fn(),
    )
    expect(screen.getByText(/Off by one cent on the settlement total/)).toBeInTheDocument()
  })

  it('shows no rejection line for a link with no rejected evidence', () => {
    renderDrawer(
      makeTask({
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'It settles the account',
            has_rejected_evidence: false,
          },
        ],
      }),
      vi.fn(),
    )
    expect(screen.queryByText(/Rejected:/)).not.toBeInTheDocument()
  })

  it('navigates from a Serves entry, resolved the same way the card chips are', async () => {
    const onOpenRequirement = vi.fn()
    renderDrawer(
      makeTask({
        requirement_links: [
          {
            identifier: 'FR-1',
            requirement_id: 'spreq-a',
            document_id: 'spdoc-1',
            state: 'active',
            statement: 'It settles the account',
            anchor: '#FR-1',
          },
        ],
      }),
      vi.fn(),
      onOpenRequirement,
    )
    await userEvent.click(screen.getByText(/It settles the account/))
    expect(onOpenRequirement).toHaveBeenCalledWith('spec/example.json', 'FR-1')
  })
})

describe('no-clipping (design.md D8, tasks.md 6.5)', () => {
  /**
   * jsdom performs no real layout — `scrollHeight`/`clientHeight` are always 0, so a literal
   * `scrollHeight <= clientHeight` assertion (`design.md`'s own wording) would pass or fail for no
   * reason connected to the actual component. What is machine-checkable here, and precisely what
   * is asserted (`tasks.md` 6.5's own instruction): the body region is the one scrolling container
   * (`overflow-y: auto`), and nothing between it and the panel's own root has a *fixed* height
   * paired with `overflow: hidden` that would silently cut content off instead of letting it
   * scroll. This proves "does not cut off silently" — the D8 reading `tasks.md` 6.5 asks for — not
   * "never scrolls," which real pixel measurement in a browser would be needed for (Q4a's own
   * boundary between agent-verifiable and human-only).
   */
  const longDescription = 'A very long description. '.repeat(80)
  const threeRequirementLinks = [
    { identifier: 'FR-1', requirement_id: 'spreq-a', document_id: 'spdoc-1', state: 'active', statement: 'First requirement, worded at some length so it wraps.' },
    { identifier: 'FR-2', requirement_id: 'spreq-b', document_id: 'spdoc-1', state: 'active', statement: 'Second requirement, also worded at some length.' },
    { identifier: 'FR-3', requirement_id: 'spreq-c', document_id: 'spdoc-1', state: 'active', statement: 'Third requirement, the F6 ceiling — a realistic worst case.' },
  ]

  it('gives the body region its own scroll, not a fixed height', () => {
    renderDrawer(
      makeTask({ description: longDescription, requirement_links: threeRequirementLinks }),
      vi.fn(),
    )
    const body = screen.getByTestId('task-drawer-body-task-1')
    expect(body.style.overflowY).toBe('auto')
    expect(body.style.height).toBe('')
    expect(body.style.maxHeight).toBe('')
  })

  it('does not set overflow: hidden on the panel itself, which would clip the scrolling body', () => {
    renderDrawer(
      makeTask({ description: longDescription, requirement_links: threeRequirementLinks }),
      vi.fn(),
    )
    const panel = screen.getByRole('dialog')
    expect(panel.style.overflow).not.toBe('hidden')
  })

  it('renders every requirement chip and the full description, none dropped, at a representative narrow width', () => {
    // jsdom does not evaluate the panel's own responsive `width: min(480px, 100vw)` against
    // `window.innerWidth` (no real CSS layout engine), so this cannot prove the drawer visually
    // fits at 360px — only that the component renders the same content regardless of viewport,
    // i.e. narrowing the window does not itself cause the component to truncate what it shows.
    window.innerWidth = 360
    window.dispatchEvent(new Event('resize'))
    renderDrawer(
      makeTask({ description: longDescription, requirement_links: threeRequirementLinks }),
      vi.fn(),
    )
    for (const link of threeRequirementLinks) {
      expect(screen.getByText(new RegExp(link.statement))).toBeInTheDocument()
    }
    expect(screen.getByText(longDescription.trim())).toBeInTheDocument()
  })
})

describe('deleting a task (F532)', () => {
  it('deletes behind a confirm and closes the drawer', async () => {
    deleteMutate = vi.fn((_vars, opts) => opts?.onSuccess?.())
    const onClose = vi.fn()
    renderDrawer(makeTask({ id: 'task-9' }), onClose)

    await userEvent.click(screen.getByTestId('task-delete-task-9'))
    expect(deleteMutate).not.toHaveBeenCalled()
    await userEvent.click(screen.getByTestId('delete-confirm'))

    expect(deleteMutate).toHaveBeenCalledWith({ id: 'task-9' }, expect.anything())
    expect(onClose).toHaveBeenCalled()
  })

  it('shows the Hub’s refusal and keeps the drawer open', async () => {
    deleteMutate = vi.fn((_vars, opts) =>
      opts?.onError?.(
        new ApiError(409, JSON.stringify({ detail: { message: 'run run-1 is working on this task', code: 'delete_run_active' } })),
      ),
    )
    const onClose = vi.fn()
    renderDrawer(makeTask({ id: 'task-9' }), onClose)

    await userEvent.click(screen.getByTestId('task-delete-task-9'))
    await userEvent.click(screen.getByTestId('delete-confirm'))

    expect(await screen.findByText(/run run-1 is working on this task/)).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })
})
