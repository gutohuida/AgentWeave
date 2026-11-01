import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import type { Task } from '@/api/tasks'
import { TasksScreen } from '@/components/tasks/TasksScreen'
import { DependencyListView } from '@/components/tasks/DependencyListView'
import { AcronymEditor } from '@/components/spec/page/SpecDocumentFacts'
import { useTaskFilterStore } from '@/store/taskFilterStore'
import { ApiError } from '@/api/client'

/**
 * Tickets have readable ids (FR-9, FR-11): the board card shows BPS-3, a search finds the task by
 * that or by its stored id, prerequisites are named by it, and a spec's acronym is edited on its
 * page with the Hub's refusal shown in its words. Tasks here are shaped like `GET /tasks` rows.
 */

const mutate = vi.fn()

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [{ name: 'worker' }] }) }))

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  return {
    ...actual,
    useSpecDocuments: () => ({ data: { documents: [] } }),
    useSpecCoverageMany: (paths: string[]) => paths.map(() => ({ data: undefined })),
    useSetDocumentAcronym: () => ({ mutate, isPending: false }),
  }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: { tasks: TASKS, total: TASKS.length, has_more: false }, isLoading: false, isError: false }),
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
    useRetryIntegration: () => ({ mutate: vi.fn() }),
  }
})

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-5a9efc6d2670',
    readable_id: 'BPS-3',
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
  makeTask(),
  makeTask({ id: 'task-0badc0ffee00', readable_id: 'BPS-4', title: 'Other work' }),
]

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

beforeEach(() => {
  mutate.mockReset()
  useTaskFilterStore.setState({ activeTaskIds: null })
})
afterEach(cleanup)

describe('the board names a task by its readable id', () => {
  it('shows BPS-3 on the card', () => {
    renderWith(<TasksScreen />)
    expect(screen.getByTestId('task-readable-id-task-5a9efc6d2670')).toHaveTextContent('BPS-3')
  })

  it.each(['bps-3', 'task-5a9efc6d2670'])('finds it by searching %s', (query) => {
    renderWith(<TasksScreen />)
    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: query } })
    expect(screen.getByText('Ship the thing')).toBeInTheDocument()
    expect(screen.queryByText('Other work')).not.toBeInTheDocument()
  })
})

describe('the dependency list names prerequisites by readable id', () => {
  it('reads BPS-3 beside the prerequisite title', () => {
    const waiting = makeTask({
      id: 'task-2',
      readable_id: 'BPS-4',
      title: 'Second',
      status: 'pending',
      prerequisites: [{ id: 'task-5a9efc6d2670', readable_id: 'BPS-3', title: 'First', status: 'in_progress' }],
    })
    renderWith(<DependencyListView tasks={[waiting]} documents={[]} onOpenTask={vi.fn()} onOpenDocument={vi.fn()} />)
    expect(screen.getByText(/Waits on BPS-3 First/)).toBeInTheDocument()
  })
})

describe('the acronym editor', () => {
  it('sends the new acronym', () => {
    renderWith(<AcronymEditor path="spec/changes/x/spec.json" acronym="BPS" />)
    fireEvent.click(screen.getByTestId('spec-acronym-edit'))
    fireEvent.change(screen.getByTestId('spec-acronym-input'), { target: { value: 'ZED' } })
    fireEvent.click(screen.getByTestId('spec-acronym-save'))
    expect(mutate.mock.calls[0][0]).toEqual({ path: 'spec/changes/x/spec.json', acronym: 'ZED' })
  })

  it("shows the Hub's refusal in its words", async () => {
    mutate.mockImplementation((_vars, options) =>
      options.onError(new ApiError(409, JSON.stringify({ detail: 'BPS cannot change: this spec has tasks named by it.' }))),
    )
    renderWith(<AcronymEditor path="p" acronym="BPS" />)
    fireEvent.click(screen.getByTestId('spec-acronym-edit'))
    fireEvent.click(screen.getByTestId('spec-acronym-save'))
    await waitFor(() => expect(screen.getByTestId('spec-acronym-refusal')).toHaveTextContent('has tasks named by it'))
  })
})
