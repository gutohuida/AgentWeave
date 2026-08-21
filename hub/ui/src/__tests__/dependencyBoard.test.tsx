import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task, TaskBoardEdge } from '@/api/tasks'
import { assignDepths, groupByDepth } from '@/lib/dependencyBoardLayout'

/**
 * `task-dependencies` task 8.1 (longest-path layer assignment), 8.2 (top-to-bottom layout with
 * edges drawn) and 8.3 (reusing `TaskCard` rather than growing a second card component).
 */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker', color_index: 0 }] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'pending',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

afterEach(cleanup)

describe('assignDepths', () => {
  it('gives a task with no prerequisites depth 0', () => {
    const tasks = [makeTask({ id: 'a' })]
    expect(assignDepths(tasks, [])).toEqual(new Map([['a', 0]]))
  })

  it('walks a chain one layer per hop', () => {
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' }), makeTask({ id: 'c' })]
    const edges: TaskBoardEdge[] = [
      { task_id: 'b', depends_on_task_id: 'a' },
      { task_id: 'c', depends_on_task_id: 'b' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBe(0)
    expect(depth.get('b')).toBe(1)
    expect(depth.get('c')).toBe(2)
  })

  it('uses the LONGEST path, not the first-declared prerequisite', () => {
    // a -> b -> d, and a -> d directly. d must sit below b (depth 2), not just below a (depth 1),
    // even though the a->d edge would place it there on its own.
    const tasks = [
      makeTask({ id: 'a' }),
      makeTask({ id: 'b' }),
      makeTask({ id: 'd' }),
    ]
    const edges: TaskBoardEdge[] = [
      { task_id: 'b', depends_on_task_id: 'a' },
      { task_id: 'd', depends_on_task_id: 'a' },
      { task_id: 'd', depends_on_task_id: 'b' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBe(0)
    expect(depth.get('b')).toBe(1)
    expect(depth.get('d')).toBe(2)
  })

  it('does not hang on a cycle, and assigns something rather than nothing', () => {
    // Should never happen — `spec_completeness` refuses `dependency_cycle` before it reaches the
    // board — but the guard is what stands between a bad row and a hung tab.
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' })]
    const edges: TaskBoardEdge[] = [
      { task_id: 'a', depends_on_task_id: 'b' },
      { task_id: 'b', depends_on_task_id: 'a' },
    ]
    const depth = assignDepths(tasks, edges)
    expect(depth.get('a')).toBeDefined()
    expect(depth.get('b')).toBeDefined()
  })

  it('ignores a prerequisite that is off this board (an import, task 8.7)', () => {
    const tasks = [makeTask({ id: 'a' })]
    const edges: TaskBoardEdge[] = [{ task_id: 'a', depends_on_task_id: 'somewhere-else' }]
    expect(assignDepths(tasks, edges).get('a')).toBe(0)
  })
})

describe('groupByDepth', () => {
  it('groups shallowest first', () => {
    const tasks = [makeTask({ id: 'a' }), makeTask({ id: 'b' }), makeTask({ id: 'c' })]
    const depth = new Map([['a', 1], ['b', 0], ['c', 1]])
    const layers = groupByDepth(tasks, depth)
    expect(layers.map((l) => l.depth)).toEqual([0, 1])
    expect(layers[0].tasks.map((t) => t.id)).toEqual(['b'])
    expect(layers[1].tasks.map((t) => t.id)).toEqual(['a', 'c'])
  })
})

function renderBoard(tasks: Task[], edges: TaskBoardEdge[]) {
  vi.doMock('@/api/tasks', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/api/tasks')>()
    return {
      ...actual,
      useTaskBoard: () => ({ data: { spec_document_id: 'spdoc-1', tasks, edges }, isLoading: false }),
    }
  })
}

describe('DependencyBoard', () => {
  it('renders each task inside the layer row matching its longest-path depth, via TaskCard', async () => {
    vi.resetModules()
    renderBoard(
      [
        makeTask({ id: 'a', title: 'Root task' }),
        makeTask({ id: 'b', title: 'Middle task' }),
        makeTask({ id: 'c', title: 'Leaf task' }),
      ],
      [
        { task_id: 'b', depends_on_task_id: 'a' },
        { task_id: 'c', depends_on_task_id: 'b' },
      ],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    expect(screen.getByTestId('dependency-board-layer-0')).toHaveTextContent('Root task')
    expect(screen.getByTestId('dependency-board-layer-1')).toHaveTextContent('Middle task')
    expect(screen.getByTestId('dependency-board-layer-2')).toHaveTextContent('Leaf task')

    // TaskCard's own status badge is present — confirms the real card is reused, not a
    // stand-in that only prints a title.
    expect(screen.getAllByText(/pending/i).length).toBeGreaterThan(0)

    // Clicking the card opens the same TaskDetailDrawer TaskCard always opens (F5).
    fireEvent.click(screen.getByText('Root task'))
    expect(screen.getByTestId('task-open-a')).toBeInTheDocument()
  })

  it('draws one line per edge whose two ends are both on the board', async () => {
    vi.resetModules()
    renderBoard(
      [makeTask({ id: 'a', title: 'Root task' }), makeTask({ id: 'b', title: 'Middle task' })],
      [
        { task_id: 'b', depends_on_task_id: 'a' },
        // Off-board reference (task 8.7's territory) — must not blow up, and draws no line yet.
        { task_id: 'b', depends_on_task_id: 'somewhere-else' },
      ],
    )
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    expect(screen.getAllByTestId('dependency-board-edge')).toHaveLength(1)
  })

  it('shows an empty state when the board has no tasks', async () => {
    vi.resetModules()
    renderBoard([], [])
    const { DependencyBoard: Board } = await import('@/components/tasks/DependencyBoard')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <Board specDocumentId="spdoc-1" />
      </QueryClientProvider>,
    )

    expect(screen.getByText('No tasks on this board')).toBeInTheDocument()
  })
})
