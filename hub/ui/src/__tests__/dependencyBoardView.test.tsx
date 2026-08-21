import { describe, expect, it, vi, afterEach } from 'vitest'
import { cleanup, render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task, TaskBoardSummary } from '@/api/tasks'

/** Task 8.5 — the document picker (design D9): one board per document, plus the standing
 *  "no document" board, each carrying its own outstanding-over-total count. */

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'A task',
    status: 'pending',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

const BOARDS: TaskBoardSummary[] = [
  { spec_document_id: 'spdoc-1', title: 'Alpha document', total: 5, outstanding: 3 },
  { spec_document_id: 'spdoc-2', title: 'Beta document', total: 2, outstanding: 0 },
  { spec_document_id: null, title: null, total: 4, outstanding: 1 },
]

function renderView(boards: TaskBoardSummary[]) {
  // Stable references, built once — a fresh literal returned from inside the mocked hook would
  // change identity on every render (the mock bypasses React Query's own cache, which is what
  // normally holds a response steady between renders) and re-trigger `DependencyBoard`'s
  // `useLayoutEffect` forever.
  const boardsResult = { data: { boards }, isLoading: false }
  const noEdges: never[] = []
  const boardsById = new Map<string | null, { data: unknown; isLoading: boolean }>([
    ['spdoc-1', { data: { spec_document_id: 'spdoc-1', tasks: [makeTask({ id: 'a', title: 'Alpha task' })], edges: noEdges }, isLoading: false }],
    ['spdoc-2', { data: { spec_document_id: 'spdoc-2', tasks: [makeTask({ id: 'b', title: 'Beta task' })], edges: noEdges }, isLoading: false }],
    [null, { data: { spec_document_id: null, tasks: [makeTask({ id: 'c', title: 'Hand-made task' })], edges: noEdges }, isLoading: false }],
  ])

  vi.doMock('@/api/tasks', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/api/tasks')>()
    return {
      ...actual,
      useTaskBoards: () => boardsResult,
      useTaskBoard: (specDocumentId: string | null) => boardsById.get(specDocumentId),
    }
  })
}

afterEach(cleanup)

describe('DependencyBoardView', () => {
  it('renders one picker entry per board, each carrying its outstanding/total count', async () => {
    vi.resetModules()
    renderView(BOARDS)
    const { DependencyBoardView } = await import('@/components/tasks/DependencyBoardView')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DependencyBoardView />
      </QueryClientProvider>,
    )

    const alpha = screen.getByTestId('dependency-board-picker-spdoc-1')
    expect(alpha).toHaveTextContent('Alpha document')
    expect(alpha).toHaveTextContent('3/5')

    const beta = screen.getByTestId('dependency-board-picker-spdoc-2')
    expect(beta).toHaveTextContent('Beta document')
    expect(beta).toHaveTextContent('0/2')

    // The standing "no document" board (design D9) — every hand-made task, named rather than
    // left blank.
    const none = screen.getByTestId('dependency-board-picker-none')
    expect(none).toHaveTextContent('No document')
    expect(none).toHaveTextContent('1/4')
  })

  it('defaults to the first document board, not the standing "no document" board', async () => {
    vi.resetModules()
    renderView(BOARDS)
    const { DependencyBoardView } = await import('@/components/tasks/DependencyBoardView')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DependencyBoardView />
      </QueryClientProvider>,
    )

    expect(screen.getByText('Alpha task')).toBeInTheDocument()
    expect(screen.getByTestId('dependency-board-picker-spdoc-1')).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches the rendered board when a different picker entry is clicked', async () => {
    vi.resetModules()
    renderView(BOARDS)
    const { DependencyBoardView } = await import('@/components/tasks/DependencyBoardView')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DependencyBoardView />
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByTestId('dependency-board-picker-none'))
    expect(screen.getByText('Hand-made task')).toBeInTheDocument()
    expect(screen.queryByText('Alpha task')).not.toBeInTheDocument()
    expect(screen.getByTestId('dependency-board-picker-none')).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows an empty state when no board has any tasks', async () => {
    vi.resetModules()
    renderView([])
    const { DependencyBoardView } = await import('@/components/tasks/DependencyBoardView')
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <DependencyBoardView />
      </QueryClientProvider>,
    )

    expect(screen.getByText('No tasks yet')).toBeInTheDocument()
    expect(screen.queryByTestId('dependency-board-picker')).not.toBeInTheDocument()
  })
})
