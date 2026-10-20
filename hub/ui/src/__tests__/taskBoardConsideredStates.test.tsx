import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * The S2 `considered` mock's board treatments, carried onto the compact board (ui-finesse): every
 * empty column still says why it is empty in its own words — now once it is opened, since an empty
 * column rests folded to a rail that names it and its count — and a card still says how its
 * requirements stand, as a tally whose rejected state is distinguishable at rest. The card's
 * description and provenance moved to the task story the card opens (ui-finesse decision: a card
 * is three lines at most).
 *
 * These are visual contracts, so they are asserted at the level a regression would actually break —
 * which element exists and which class carries it — not by re-reading computed styles jsdom does
 * not compute.
 */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

const COVERAGE_RESPONSE = {
  requirements: [
    { identifier: 'REQ-118', requirement_id: 'spreq-118', document_id: 'doc-1', state: 'verified' },
    { identifier: 'REQ-090', requirement_id: 'spreq-090', document_id: 'doc-1', state: 'rejected' },
  ],
  diagnostics: [],
  totals: {},
  integration: {},
  unserved: [],
}

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [{ id: 'doc-1', path: 'spec/thing.json' }] } }),
  useSpecCoverageMany: (paths: string[]) => paths.map(() => ({ data: COVERAGE_RESPONSE })),
}))

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({
      data: { tasks: TASKS, total: TASKS.length, has_more: false },
      isLoading: false,
      isError: false,
    }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
    useRetryIntegration: () => ({ mutate: vi.fn() }),
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
      <TasksScreen />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useTaskFilterStore.setState({ activeTaskIds: null })
})

afterEach(cleanup)

describe('S2 — per-column empty states', () => {
  it('rests an empty column folded, named with its count, for a screen reader too', () => {
    renderBoard()

    expect(screen.getByRole('button', { name: 'Pending, 0 tasks. Show column' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assigned, 0 tasks. Show column' })).toHaveAttribute('title', 'Assigned: nothing here')
    // The column with work is open, not a rail.
    expect(screen.queryByRole('button', { name: /^In progress, .* Show column$/ })).not.toBeInTheDocument()
  })

  it('gives each opened empty column its own description, not one shared string', () => {
    renderBoard()

    fireEvent.click(screen.getByRole('button', { name: 'Assigned, 0 tasks. Show column' }))
    fireEvent.click(screen.getByRole('button', { name: 'Under review, 0 tasks. Show column' }))
    fireEvent.click(screen.getByRole('button', { name: 'Approved, 0 tasks. Show column' }))

    expect(screen.getByTestId('task-column-empty-assigned')).toHaveTextContent('Assign a pending task to move it here.')
    expect(screen.getByTestId('task-column-empty-under_review')).toHaveTextContent('Completed work waits here for a verdict.')
    expect(screen.getByTestId('task-column-empty-approved')).toHaveTextContent('Nothing approved yet.')
    expect(screen.queryByTestId('task-column-empty-in_progress')).not.toBeInTheDocument()
    expect(screen.queryByText('No tasks')).not.toBeInTheDocument()
  })
})

describe('S2 — a card says how its requirements stand', () => {
  it('tallies verified over total, and marks a rejected one at rest', () => {
    renderBoard()

    const tally = screen.getByText('1/2 FR')
    expect(tally).toHaveClass('aw-task-card-reqs')
    expect(tally).toHaveAttribute('data-rejected', 'true')
    expect(tally).toHaveAttribute('data-complete', 'false')
    expect(tally).toHaveAttribute('title', '1 of 2 requirements verified, 1 rejected')
  })
})
