import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { useBoardScopeStore } from '@/store/boardScopeStore'
import { useConfigStore } from '@/store/configStore'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * F1129: the board's Building scope and a spec's way into the board. Modelled on boardScope.test.tsx.
 * Spec B alone has a build running (the documents list says so with `build`).
 * The board's scope (FR-1..FR-6, FR-8, FR-9). The mocked task list answers as the route does:
 * oldest first, narrowed by the same parameters (`spec_document_id`, `no_spec`,
 * `exclude_archived_completed`), so a scope that asked the wrong question gets the wrong tasks.
 */

let tasks: Task[] = []
let archived = new Set<string>()
let agents: { name: string; color_index: number }[] = []
let cap: number | null = null

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: agents }) }))
vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({
    data: {
      documents: [
        { id: 'spec-a', title: 'Alpha plan', path: 'spec/changes/a/spec.json' },
        { id: 'spec-b', title: 'Beta plan', path: 'spec/changes/b/spec.json', build: { id: 'build-b', done: 0, total: 2 } },
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
      specDocumentIds?: string[]
    }) => {
      const done = ['approved', 'rejected']
      const rows = [...tasks]
        .sort((x, y) => x.created_at.localeCompare(y.created_at))
        .filter((t) => {
          if (options?.specDocumentIds) return options.specDocumentIds.includes(t.spec_document_id ?? '')
          if (options?.specDocumentId) return t.spec_document_id === options.specDocumentId
          if (options?.noSpec) return !t.spec_document_id
          if (options?.excludeArchivedCompleted)
            return !(t.spec_document_id && archived.has(t.spec_document_id) && done.includes(t.status))
          return true
        })
      // An unscoped page stops at `cap`, oldest first, as the route's page does past 1000 tasks;
      // a scoped query loads every page of its scope (`useTasks`).
      const scoped = Boolean(options?.specDocumentId || options?.noSpec || options?.specDocumentIds)
      if (cap !== null && !scoped) {
        return {
          data: { tasks: rows.slice(0, cap), total: rows.length, has_more: rows.length > cap },
          isLoading: false,
          isError: false,
        }
      }
      return { data: { tasks: rows, total: rows.length, has_more: false }, isLoading: false, isError: false }
    },
    useTaskBoards: () => {
      const totals = new Map<string | null, number>()
      for (const t of tasks) totals.set(t.spec_document_id ?? null, (totals.get(t.spec_document_id ?? null) ?? 0) + 1)
      const titles: Record<string, string> = { 'spec-a': 'Alpha plan', 'spec-b': 'Beta plan', 'spec-c': 'Gamma plan', 'spec-new': 'Newest plan' }
      return {
        data: {
          boards: [...totals].map(([id, total]) => ({
            spec_document_id: id,
            title: id ? (titles[id] ?? id) : null,
            total,
            outstanding: total,
          })),
        },
        error: null,
      }
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
  cap = null
  a =[task('A one', 'spec-a'), task('A two', 'spec-a', { status: 'approved' })]
  b = [task('B one', 'spec-b'), task('B two', 'spec-b')]
  free = [task('Free one', null), task('Free two', null)]
  tasks = [...a, ...b, ...free]
  archived = new Set(['spec-a'])
  useBoardScopeStore.setState({ scopes: {} })
  useTaskFilterStore.setState({ activeTaskIds: null, pendingOpenTaskId: null })
  useConfigStore.setState({ selectedProjectId: 'proj-1' })
})
afterEach(cleanup)

describe('the Building scope and the spec scope (F1129)', () => {
  it('offers Building in one click and shows every task of a spec whose build runs, whatever its status', () => {
    b[1].status = 'approved'
    renderBoard()
    // Spec A is archived, so its finished task is not on the unscoped board.
    expect(shown()).toEqual(ids(tasks.filter((t) => t !== a[1])))

    choose('building')

    expect(shown()).toEqual(ids(b))
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('Building · 2 tasks')
    fireEvent.click(screen.getByTestId('board-scope-clear'))
    // Spec A is archived, so its finished task is not on the unscoped board.
    expect(shown()).toEqual(ids(tasks.filter((t) => t !== a[1])))
  })

  it('counts the specs with a build running on the option', () => {
    renderBoard()
    fireEvent.click(screen.getByTestId('board-scope'))
    expect(screen.getByTestId('board-scope-option-building')).toHaveTextContent('1')
  })

  it('a spec scope set from the spec screen shows exactly that spec and names it in the banner', () => {
    act(() => useBoardScopeStore.getState().setScope('proj-1', { kind: 'spec', id: 'spec-a' }))
    renderBoard()
    expect(shown()).toEqual(ids(a))
    expect(screen.getByTestId('board-scope-name')).toHaveTextContent('Alpha plan')
  })
})
