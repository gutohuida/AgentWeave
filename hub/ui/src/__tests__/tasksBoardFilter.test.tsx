import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksBoard } from '@/components/tasks/TasksBoard'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * The other half of F4's cross-tab navigation: a coverage row's task-count link sets which tasks
 * the board shows (`SpecCoverageBar` → `App.tsx` → this store → `TasksBoard`), rather than the
 * board inventing a second filtering mechanism of its own (`design.md` D7).
 */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [] } }),
}))

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: TASKS, isLoading: false }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
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
  makeTask({ id: 'task-1', title: 'Settle the account', status: 'in_progress' }),
  makeTask({ id: 'task-2', title: 'Round consistently', status: 'assigned' }),
  makeTask({ id: 'task-3', title: 'Unrelated work', status: 'pending' }),
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

describe('the board can be filtered from outside itself', () => {
  it('shows every task when nothing set a filter', () => {
    renderBoard()
    expect(screen.getByText('Settle the account')).toBeInTheDocument()
    expect(screen.getByText('Round consistently')).toBeInTheDocument()
    expect(screen.getByText('Unrelated work')).toBeInTheDocument()
    expect(screen.queryByTestId('tasks-requirement-filter-banner')).not.toBeInTheDocument()
  })

  it('shows only the tasks named by the store, with a banner naming the count', () => {
    useTaskFilterStore.getState().setActiveTaskIds(['task-1', 'task-2'])
    renderBoard()

    expect(screen.getByTestId('tasks-requirement-filter-banner')).toHaveTextContent('2 tasks')
    expect(screen.getByText('Settle the account')).toBeInTheDocument()
    expect(screen.getByText('Round consistently')).toBeInTheDocument()
    expect(screen.queryByText('Unrelated work')).not.toBeInTheDocument()
  })

  it('clearing the filter restores every task', () => {
    useTaskFilterStore.getState().setActiveTaskIds(['task-1'])
    renderBoard()

    expect(screen.queryByText('Unrelated work')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('tasks-requirement-filter-clear'))

    expect(screen.getByText('Unrelated work')).toBeInTheDocument()
    expect(screen.queryByTestId('tasks-requirement-filter-banner')).not.toBeInTheDocument()
  })
})
