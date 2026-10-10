import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { Task } from '@/api/tasks'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * The drawer's "Depends on" section (F571, `a-tasks-prerequisites-can-be-declared-at-creation-and-
 * in-its-drawer`, criterion `drawer-picker`).
 *
 * The Hub could always record "B needs A" (`POST /tasks/{id}/dependencies`) and nothing on screen
 * reached it. What matters here: the section says what the task waits on (with each one's status),
 * says "depends on nothing" rather than staying blank, offers every *other* task that is not
 * already a prerequisite — cycle-forming ones included, since the Hub is the one that knows — and
 * shows the Hub's own refusal sentence when it declines.
 */

const addDependency = vi.fn()
const removeDependency = vi.fn()
let allTasks: Task[] = []
let tasksError: Error | null = null

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useTasks: () =>
      tasksError
        ? { data: undefined, error: tasksError }
        : { data: { tasks: allTasks, total: allTasks.length, has_more: false }, error: null },
    useAddTaskDependency: () => ({ mutate: addDependency }),
    useRemoveTaskDependency: () => ({ mutate: removeDependency }),
  }
})

vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [] }) }))

function makeTask(id: string, overrides: Partial<Task> = {}): Task {
  return {
    id,
    project_id: 'proj-test',
    title: `Title of ${id}`,
    status: 'pending',
    priority: 'medium',
    created_at: '2026-10-10T10:00:00Z',
    updated: '2026-10-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    prerequisites: [],
    dependents: [],
    ...overrides,
  }
}

async function renderOpen(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByTestId(`task-open-${task.id}`))
}

beforeEach(() => {
  addDependency.mockReset()
  removeDependency.mockReset()
  allTasks = []
  tasksError = null
})

afterEach(cleanup)

describe('the drawer says what a task depends on', () => {
  it('says "depends on nothing" when there are no prerequisites', async () => {
    const task = makeTask('task-b')
    allTasks = [task]
    await renderOpen(task)

    expect(screen.getByTestId('task-dependencies-empty-task-b')).toHaveTextContent(
      'depends on nothing',
    )
  })

  it('lists each prerequisite with its title and status, and no empty line', async () => {
    const task = makeTask('task-b', {
      prerequisites: [{ id: 'task-a', title: 'Build the base', status: 'in_progress' }],
    })
    allTasks = [task, makeTask('task-a')]
    await renderOpen(task)

    const row = screen.getByTestId('task-dependency-task-b-task-a')
    expect(row).toHaveTextContent('Build the base')
    expect(row).toHaveTextContent(/in.progress/i)
    expect(screen.queryByTestId('task-dependencies-empty-task-b')).not.toBeInTheDocument()
  })

  it('removes a prerequisite from its row', async () => {
    const task = makeTask('task-b', {
      prerequisites: [{ id: 'task-a', title: 'Build the base', status: 'pending' }],
    })
    allTasks = [task, makeTask('task-a')]
    await renderOpen(task)
    await userEvent.click(screen.getByTestId('task-dependency-remove-task-b-task-a'))

    expect(removeDependency).toHaveBeenCalledWith(
      { id: 'task-b', dependsOn: 'task-a' },
      expect.anything(),
    )
  })
})

describe('the picker', () => {
  it('offers every other task that is not already a prerequisite, labelled title (id)', async () => {
    const task = makeTask('task-b', {
      prerequisites: [{ id: 'task-a', title: 'Title of task-a', status: 'pending' }],
    })
    allTasks = [task, makeTask('task-a'), makeTask('task-c')]
    await renderOpen(task)

    const options = Array.from(
      screen.getByTestId('task-dependency-picker-task-b').querySelectorAll('option'),
    ).map((o) => [o.getAttribute('value'), o.textContent])
    // Not itself, not its existing prerequisite; the blank first option is the unchosen state.
    expect(options).toContainEqual(['task-c', 'Title of task-c (task-c)'])
    expect(options.map(([v]) => v)).not.toContain('task-b')
    expect(options.map(([v]) => v)).not.toContain('task-a')
  })

  it('does not add until something is chosen', async () => {
    const task = makeTask('task-b')
    allTasks = [task, makeTask('task-c')]
    await renderOpen(task)

    expect(screen.getByTestId('task-dependency-add-task-b')).toBeDisabled()
  })

  it('sends the chosen task as the new prerequisite', async () => {
    const task = makeTask('task-b')
    allTasks = [task, makeTask('task-c')]
    await renderOpen(task)
    await userEvent.selectOptions(screen.getByTestId('task-dependency-picker-task-b'), 'task-c')
    await userEvent.click(screen.getByTestId('task-dependency-add-task-b'))

    expect(addDependency).toHaveBeenCalledWith(
      { id: 'task-b', dependsOn: 'task-c' },
      expect.anything(),
    )
  })

  it("shows the Hub's refusal sentence when the add is refused", async () => {
    const sentence =
      'task task-b already depends on task-a, directly or through others, so this would make each wait on the other forever.'
    addDependency.mockImplementation((_vars, opts) =>
      opts.onError(new ApiError(409, JSON.stringify({ detail: sentence }))),
    )
    const task = makeTask('task-a')
    allTasks = [task, makeTask('task-b')]
    await renderOpen(task)
    await userEvent.selectOptions(screen.getByTestId('task-dependency-picker-task-a'), 'task-b')
    await userEvent.click(screen.getByTestId('task-dependency-add-task-a'))

    await waitFor(() =>
      expect(screen.getByTestId('task-dependency-refusal-task-a')).toHaveTextContent(sentence),
    )
  })

  it('says the task list could not be read, rather than offering an empty picker', async () => {
    // F577: the picker's own task list failing looked exactly like a project with no other tasks.
    tasksError = new ApiError(500, JSON.stringify({ detail: 'database is locked' }))
    const task = makeTask('task-b')
    await renderOpen(task)

    expect(screen.getByTestId('task-dependency-picker-error-task-b')).toHaveTextContent(
      'database is locked',
    )
  })
})
