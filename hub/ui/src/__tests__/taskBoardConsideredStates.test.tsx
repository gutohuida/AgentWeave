import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * The S2 `considered` mock's board treatments, which shipped as the `restrained` variant or not at
 * all: per-column empty states, the description's second line and its fade, and requirement chips
 * that are distinguishable from informational badges at rest.
 *
 * These are visual contracts, so they are asserted at the level a regression would actually break —
 * which element exists and which class carries it — not by re-reading computed styles jsdom does
 * not compute.
 */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [{ id: 'doc-1', path: 'spec/thing.html' }] } }),
}))

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: TASKS, isLoading: false, isError: false }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

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

const TASKS: Task[] = [
  makeTask({
    id: 'task-1',
    title: 'Settle the account',
    status: 'in_progress',
    description: 'A description long enough that the clamp is what decides how much of it is read.',
    assigner: 'reviewer',
    requirement_ids: ['REQ-118', 'REQ-090'],
    requirement_links: [
      { identifier: 'REQ-118', document_id: 'doc-1', anchor: '#req-118', statement: 'It settles.', has_rejected_evidence: false },
      { identifier: 'REQ-090', document_id: 'doc-1', anchor: '#req-090', statement: 'It rounds.', has_rejected_evidence: true },
    ],
  } as Partial<Task>),
]

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TasksBoard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useTaskFilterStore.setState({ activeTaskIds: null })
})

afterEach(cleanup)

describe('S2 — per-column empty states', () => {
  it('gives every empty column an icon, a title and its own description, not one shared string', () => {
    renderBoard()

    // Six of the seven columns are empty here, which is the point: this treatment is the
    // most-repeated element on the board, so it cannot be seven copies of "No tasks".
    const assigned = screen.getByTestId('task-column-empty-assigned')
    expect(assigned).toHaveTextContent('Nothing assigned')
    expect(assigned).toHaveTextContent('Assign a pending task to move it here.')
    expect(assigned.querySelector('.task-column-empty-icon')).not.toBeNull()

    // Per column, not shared — the review column says what it is waiting for, which is a
    // different fact from what the pending column says.
    expect(screen.getByTestId('task-column-empty-under_review')).toHaveTextContent('Nothing to review')
    expect(screen.getByTestId('task-column-empty-approved')).toHaveTextContent('Nothing approved')

    // The one populated column has no empty state at all.
    expect(screen.queryByTestId('task-column-empty-in_progress')).not.toBeInTheDocument()

    // The literal placeholder this replaces is gone.
    expect(screen.queryByText('No tasks')).not.toBeInTheDocument()
  })

  it('still names the column for a screen reader', () => {
    renderBoard()
    expect(screen.getByLabelText('Pending has no tasks')).toBeInTheDocument()
  })
})

describe('S2 — the card keeps its second description line', () => {
  it('clamps to two lines with a fade, not to one', () => {
    renderBoard()

    const description = screen.getByText(/A description long enough/)
    // Clamping harder was a density regression (IDENTITY clause 6).
    expect(description).toHaveClass('line-clamp-2')
    expect(description).not.toHaveClass('line-clamp-1')
    // The affordance the clamp never had: something at rest saying more text exists.
    expect(description.parentElement).toHaveClass('task-card-desc-wrap')
    expect(description.parentElement?.querySelector('.task-card-desc-fade')).not.toBeNull()
  })
})

describe('S2 — a requirement chip does not look like an informational badge', () => {
  it('gives requirement chips their own class and informational text its own', () => {
    renderBoard()

    const chip = screen.getByTestId('task-requirement-chip-task-1-REQ-118')
    expect(chip).toHaveClass('task-chip-req')
    expect(chip).not.toHaveClass('rejected')

    // Rejected evidence is a modifier on the same chip, not a different kind of element.
    const rejected = screen.getByTestId('task-requirement-chip-task-1-REQ-090')
    expect(rejected).toHaveClass('task-chip-req')
    expect(rejected).toHaveClass('rejected')

    // Provenance is a fact, not an action — flat text rather than a bordered pill.
    const provenance = screen.getByText('from: reviewer')
    expect(provenance).toHaveClass('task-chip-info')
    expect(provenance).not.toHaveClass('task-chip-req')
  })
})
