import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { useBoardScopeStore } from '@/store/boardScopeStore'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * The board's scope (FR-1..FR-6, FR-8, FR-9). The mocked task list answers as the route does:
 * oldest first, narrowed by the same parameters (`spec_document_id`, `no_spec`,
 * `exclude_archived_completed`), so a scope that asked the wrong question gets the wrong tasks.
 */

let tasks: Task[] = []
let archived = new Set<string>()
let agents: { name: string; color_index: number }[] = []

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: agents }) }))
vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({
    data: {
      documents: [
        { id: 'spec-a', title: 'Alpha plan', path: 'spec/changes/a/spec.json' },
        { id: 'spec-b', title: 'Beta plan', path: 'spec/changes/b/spec.json' },
        { id: 'spec-c', title: 'Gamma plan', path: 'spec/changes/c/spec.json' },
      ],
    },
  }),
  useSpecCoverageMany: (paths: string[]) => paths.map(() => ({ data: undefined })),
}))
vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: (options?: {
      excludeArchivedCompleted?: boolean
      specDocumentId?: string
      noSpec?: boolean
    }) => {
      const done = ['approved', 'rejected']
      const rows = [...tasks]
        .sort((x, y) => x.created_at.localeCompare(y.created_at))
        .filter((t) => {
          if (options?.specDocumentId) return t.spec_document_id === options.specDocumentId
          if (options?.noSpec) return !t.spec_document_id
          if (options?.excludeArchivedCompleted)
            return !(t.spec_document_id && archived.has(t.spec_document_id) && done.includes(t.status))
          return true
        })
      return { data: { tasks: rows, total: rows.length, has_more: false }, isLoading: false, isError: false }
    },
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
    useRetryIntegration: () => ({ mutate: vi.fn() }),
    useTask: () => ({ data: undefined, error: null }),
  }
})

let counter = 0
function task(title: string, spec: string | null, overrides: Partial<Task> = {}): Task {
  counter += 1
  return {
    id: `task-${String(counter).padStart(2, '0')}`,
    project_id: 'proj-1',
    title,
    status: 'pending',
    priority: 'medium',
    created_at: `2026-08-10T10:${String(counter).padStart(2, '0')}:00Z`,
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    spec_document_id: spec,
    ...overrides,
  }
}

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TasksScreen />
    </QueryClientProvider>,
  )
}

const shown = () =>
  [...document.querySelectorAll('[data-task-id]')].map((n) => n.getAttribute('data-task-id')).sort()
const ids = (list: Task[]) => list.map((t) => t.id).sort()
const choose = (key: string) => {
  fireEvent.click(screen.getByTestId('board-scope'))
  fireEvent.click(screen.getByTestId(`board-scope-option-${key}`))
}

let a: Task[]
let b: Task[]
let free: Task[]

beforeEach(() => {
  counter = 0
  localStorage.clear()
  agents = []
  a = [task('A one', 'spec-a'), task('A two', 'spec-a', { status: 'approved' })]
  b = [task('B one', 'spec-b'), task('B two', 'spec-b')]
  free = [task('Free one', null), task('Free two', null)]
  tasks = [...a, ...b, ...free]
  archived = new Set(['spec-a'])
  useBoardScopeStore.setState({ scopes: {} })
  useTaskFilterStore.setState({ activeTaskIds: null, pendingOpenTaskId: null })
  useConfigStore.setState({ selectedProjectId: 'proj-1' })
})
afterEach(cleanup)

describe('the board scope', () => {
  it('offers All, No spec and each spec that has tasks with its count, and narrows as typed (ac-picker-lists)', () => {
    renderBoard()
    fireEvent.click(screen.getByTestId('board-scope'))
    expect(screen.getByTestId('board-scope-option-all')).toBeInTheDocument()
    expect(screen.getByTestId('board-scope-option-none')).toHaveTextContent('2')
    expect(screen.getByTestId('board-scope-option-spec-a')).toHaveTextContent('Alpha plan')
    expect(screen.getByTestId('board-scope-option-spec-a')).toHaveTextContent('2')
    expect(screen.getByTestId('board-scope-option-spec-b')).toHaveTextContent('Beta plan')
    expect(screen.queryByTestId('board-scope-option-spec-c')).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId('board-scope-filter'), { target: { value: 'alph' } })
    expect(screen.getByTestId('board-scope-option-spec-a')).toBeInTheDocument()
    expect(screen.queryByTestId('board-scope-option-spec-b')).not.toBeInTheDocument()
    expect(screen.queryByTestId('board-scope-option-all')).not.toBeInTheDocument()
  })

  it("shows an archived spec's finished and pending tasks when chosen, and hides its finished ones under All (ac-one-spec, ac-all)", () => {
    renderBoard()
    expect(shown()).toEqual(ids([a[0]!, ...b, ...free]))
    choose('spec-a')
    expect(shown()).toEqual(ids(a))
    choose('all')
    expect(shown()).toEqual(ids([a[0]!, ...b, ...free]))
  })

  it('shows exactly the tasks with no spec (ac-no-spec)', () => {
    renderBoard()
    choose('none')
    expect(shown()).toEqual(ids(free))
  })

  it('names the scope and its count, and one click returns to All (ac-says)', () => {
    renderBoard()
    expect(screen.queryByTestId('board-scope-name')).not.toBeInTheDocument()
    choose('spec-a')
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('Alpha plan')
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('2 tasks')
    fireEvent.click(screen.getByTestId('board-scope-clear'))
    expect(screen.queryByTestId('board-scope-name')).not.toBeInTheDocument()
    expect(shown()).toEqual(ids([a[0]!, ...b, ...free]))
  })

  it('counts the agent chips within the scope, and applies the chip to it (ac-combined)', () => {
    agents = [
      { name: 'Developer', color_index: 0 },
      { name: 'QA', color_index: 1 },
    ]
    counter = 0
    tasks = [
      task('A1', 'spec-a', { assignee: 'Developer' }),
      task('A2', 'spec-a', { assignee: 'Developer' }),
      task('A3', 'spec-a', { assignee: 'QA' }),
      task('B1', 'spec-b', { assignee: 'Developer' }),
    ]
    renderBoard()
    choose('spec-a')
    const chip = screen.getByRole('button', { name: /^Developer/ })
    expect(within(chip).getByText('2')).toBeInTheDocument()
    fireEvent.click(chip)
    expect(shown()).toEqual(['task-01', 'task-02'])
  })

  it("remembers each project's own scope across a reload (ac-remembers)", () => {
    renderBoard()
    choose('spec-a')
    cleanup()
    act(() => useConfigStore.setState({ selectedProjectId: 'proj-2' }))
    renderBoard()
    choose('none')
    cleanup()
    useBoardScopeStore.setState({ scopes: {} }) // a reload keeps only local storage
    renderBoard()
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('No spec')
    cleanup()
    act(() => useConfigStore.setState({ selectedProjectId: 'proj-1' }))
    renderBoard()
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('Alpha plan')
  })

  it('opens as All when the remembered spec has no task any more (ac-stale-scope)', () => {
    localStorage.setItem('aw.boardScope.proj-1', JSON.stringify({ kind: 'spec', id: 'spec-gone' }))
    renderBoard()
    expect(screen.queryByTestId('board-scope-name')).not.toBeInTheDocument()
    expect(shown()).toEqual(ids([a[0]!, ...b, ...free]))
  })

  it('lets a task-id narrowing override the scope and leaves the remembered scope alone (ac-override)', () => {
    renderBoard()
    choose('none')
    act(() => useTaskFilterStore.getState().setActiveTaskIds([a[0]!.id, a[1]!.id]))
    expect(shown()).toEqual(ids(a))
    expect(screen.getByTestId('tasks-requirement-filter-banner')).toBeInTheDocument()
    expect(JSON.parse(localStorage.getItem('aw.boardScope.proj-1')!)).toEqual({ kind: 'none' })
    fireEvent.click(screen.getByTestId('tasks-requirement-filter-clear'))
    expect(shown()).toEqual(ids(free))
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('No spec')
  })

  it('opens scoped to a spec set from its page, and keeps it (ac-spec-link)', () => {
    act(() => useBoardScopeStore.getState().setScope('proj-1', { kind: 'spec', id: 'spec-b' }))
    renderBoard()
    expect(shown()).toEqual(ids(b))
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('Beta plan')
    expect(JSON.parse(localStorage.getItem('aw.boardScope.proj-1')!)).toEqual({ kind: 'spec', id: 'spec-b' })
  })
})
