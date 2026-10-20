import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ApiError } from '@/api/client'
import type { Task } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { useToastStore } from '@/lib/toast'
import { useTaskFilterStore } from '@/store/taskFilterStore'

/**
 * The Tasks screen's own duties beyond the board's drawing: a move the Hub refuses says why (in a
 * toast, where it used to be a dismissable strip), the command palette's open-task intent opens the
 * drawer once the board mounts (D3), and the Dependencies lens is one segment away.
 */

let agentsError: Error | null = null
let transitionsError: Error | null = null
vi.mock('@/api/agents', () => ({
  useAgents: () => (agentsError ? { data: undefined, error: agentsError } : { data: [{ name: 'worker', color_index: 1 }], error: null }),
}))
vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: { documents: [{ id: 'doc-1', title: 'Watcher', path: 'spec/w.json' }] } }),
  useSpecCoverageMany: (paths: string[]) => paths.map(() => ({ data: undefined })),
}))

let updateImpl: (args: unknown, opts: { onError?: (e: unknown) => void }) => void = () => undefined
const startWork = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: { tasks: TASKS, total: TASKS.length, has_more: false }, isLoading: false, isError: false }),
    useAllowedTransitions: () =>
      transitionsError ? { data: undefined, error: transitionsError } : { data: { actor_kind: 'operator', transitions: { pending: ['assigned'] } }, error: null },
    useUpdateTask: () => ({ mutate: (a: unknown, o: { onError?: (e: unknown) => void }) => updateImpl(a, o), isPending: false }),
    useStartWorkOnTask: () => ({ mutate: startWork }),
    useRetryIntegration: () => ({ mutate: vi.fn() }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
  }
})
vi.mock('@/components/tasks/TaskDetailDrawer', () => ({
  TaskDetailDrawer: ({ task }: { task: Task | null }) => (task ? <div data-testid="drawer">{task.title}</div> : null),
}))

const TASKS: Task[] = [
  {
    id: 'task-1',
    project_id: 'p',
    title: 'Lay the pipe',
    status: 'pending',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    spec_document_id: 'doc-1',
  },
]

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TasksScreen />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useTaskFilterStore.setState({ activeTaskIds: null, pendingOpenTaskId: null })
  useToastStore.setState({ items: [] })
  updateImpl = () => undefined
  agentsError = null
  transitionsError = null
})
afterEach(cleanup)

describe('the tasks screen', () => {
  it('says the agents could not be read, so the filter and Start work are not taken as "nobody"', () => {
    agentsError = new Error('500')
    renderScreen()
    expect(screen.getByTestId('query-error-notice')).toHaveTextContent('Couldn’t read the agents from the Hub')
  })

  it('says a keyboard move was not made because the allowed moves are unread, not that none exist', () => {
    transitionsError = new Error('500')
    renderScreen()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Open Lay the pipe' }), { key: 'ArrowRight', ctrlKey: true })
    expect(screen.getByText(/The allowed moves could not be read from the Hub, so Lay the pipe was not moved\./)).toBeInTheDocument()
    expect(screen.queryByText(/No allowed status is available/)).toBeNull()
  })

  it('says why the Hub refused a move', () => {
    updateImpl = (_args, opts) => opts.onError?.(new ApiError(409, JSON.stringify({ detail: 'A prerequisite is not approved.' })))
    renderScreen()

    fireEvent.keyDown(screen.getByRole('button', { name: 'Open Lay the pipe' }), { key: 'ArrowRight', ctrlKey: true })

    const [toast] = useToastStore.getState().items
    expect(toast?.title).toBe('Could not move Lay the pipe')
    expect(toast?.tone).toBe('error')
  })

  it('starts the chosen agent on the task, binding the run to it', () => {
    startWork.mockReset()
    renderScreen()

    fireEvent.keyDown(screen.getByRole('button', { name: 'Start work on Lay the pipe' }), { key: 'Enter' })
    fireEvent.click(screen.getByRole('menuitem', { name: 'Start worker on this' }))

    expect(startWork).toHaveBeenCalledWith(
      expect.objectContaining({ taskId: 'task-1', agent: 'worker', title: 'Lay the pipe' }),
      expect.anything(),
    )
  })

  it('opens the drawer for a task the command palette chose before the board mounted', () => {
    useTaskFilterStore.getState().setPendingOpenTaskId('task-1')
    renderScreen()
    expect(screen.getByTestId('drawer')).toHaveTextContent('Lay the pipe')
    expect(useTaskFilterStore.getState().pendingOpenTaskId).toBeNull()
  })

  it('opens a card into the drawer', () => {
    renderScreen()
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Open Lay the pipe' }))
    })
    expect(screen.getByTestId('drawer')).toHaveTextContent('Lay the pipe')
  })

  it('switches to the dependency chains', () => {
    renderScreen()
    fireEvent.click(screen.getByRole('radio', { name: 'Dependencies' }))
    expect(screen.getByRole('region', { name: 'Watcher' })).toBeInTheDocument()
  })
})
