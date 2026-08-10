import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TasksBoard } from '@/components/tasks/TasksBoard'

/**
 * The board renders one column per status. `blocked` has none, by decision (R3) — so unless the
 * In Progress column claims it, a task that parks itself disappears from the board entirely, which
 * is worse than any labelling problem it was meant to solve.
 */

let tasks: Task[] = []

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: tasks, isLoading: false }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [] }),
}))

function makeTask(id: string, status: string, title: string): Task {
  return {
    id,
    project_id: 'proj-test',
    title,
    status,
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
  }
}

function renderBoard(rows: Task[]) {
  tasks = rows
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TasksBoard />
    </QueryClientProvider>,
  )
}

afterEach(cleanup)

describe('a waiting task stays on the board', () => {
  it('is still visible, rather than falling through the gap between columns', () => {
    renderBoard([makeTask('t1', 'blocked', 'Waiting work')])

    expect(screen.getByText('Waiting work')).toBeTruthy()
  })

  it('is counted in In Progress, because that is where it is shown', () => {
    renderBoard([
      makeTask('t1', 'blocked', 'Waiting work'),
      makeTask('t2', 'in_progress', 'Running work'),
    ])

    const header = screen.getByText('In Progress').parentElement
    expect(header?.textContent).toContain('2')
  })

  it('adds no ninth column', () => {
    renderBoard([makeTask('t1', 'blocked', 'Waiting work')])

    expect(screen.queryByText('Blocked')).toBeNull()
  })

  it('puts waiting work above running work — it is the part that needs the operator', () => {
    renderBoard([
      makeTask('t1', 'in_progress', 'Running work'),
      makeTask('t2', 'blocked', 'Waiting work'),
    ])

    const waiting = screen.getByText('Waiting work')
    const running = screen.getByText('Running work')
    // `compareDocumentPosition` returns DOCUMENT_POSITION_FOLLOWING (4) when `running` comes after.
    expect(waiting.compareDocumentPosition(running) & 4).toBeTruthy()
  })
})
