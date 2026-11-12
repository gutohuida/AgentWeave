import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task, TaskMoves } from '@/api/tasks'
import { BoardView } from '@/components/tasks/BoardView'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * `tasks-outside-a-flow-move-freely`, FR-9 and FR-10: the drawer offers the actions the moves route
 * answers with (shapes as `GET .../tasks/{id}/moves` returns them), and the board closes several
 * selected tasks at once, naming the one the Hub refuses.
 */

const close = vi.fn()
const updateTask = vi.fn()
let moves: TaskMoves

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useTaskMoves: () => ({ data: moves }),
    useUpdateTask: () => ({ mutate: updateTask, isPending: false }),
    useLandTask: () => ({ mutate: vi.fn(), isPending: false }),
    useCloseTasks: () => ({ mutate: close, isPending: false }),
    useTaskChecks: () => ({ data: { configured: true, running: false, runs: [] } }),
    useRerunTaskChecks: () => ({ mutate: vi.fn(), isPending: false }),
    useTaskIntegrationPreview: () => ({ data: null }),
  }
})

const task = (id: string, status = 'completed'): Task => ({
  id,
  readable_id: id.toUpperCase(),
  project_id: 'proj-test',
  title: `Task ${id}`,
  status,
  assignee: 'D',
  priority: 'medium',
  created_at: '2026-11-12T10:00:00Z',
  updated: '2026-11-12T10:00:00Z',
  divergence_policy: 'surface',
  has_open_divergence: false,
})

const wrap = (ui: React.ReactNode) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {ui}
  </QueryClientProvider>
)

beforeEach(() => {
  close.mockReset()
  updateTask.mockReset()
})
afterEach(cleanup)

async function drawerFor(id: string) {
  render(wrap(<TaskCardHost task={task(id)} />))
  const user = userEvent.setup()
  await user.click(screen.getByTestId(`task-open-${id}`))
  return user
}

describe('the drawer', () => {
  it('offers a loose completed task approve, send back, done elsewhere and cancel', async () => {
    moves = {
      task_id: 'loose',
      status: 'completed',
      moves: ['approved', 'revision_needed'],
      loose: true,
      closes: ['done_elsewhere', 'cancelled'],
    }
    await drawerFor('loose')
    expect(screen.getByTestId('task-approve-loose')).toBeTruthy()
    expect(screen.getByTestId('task-send-back-loose')).toBeTruthy()
    expect(screen.getByTestId('task-close-done-elsewhere-loose')).toBeTruthy()
    expect(screen.getByTestId('task-cancel-loose')).toBeTruthy()
  })

  it("offers a flow task only what its rules allow", async () => {
    moves = { task_id: 'flow', status: 'completed', moves: ['under_review'], loose: false, closes: [] }
    await drawerFor('flow')
    expect(screen.queryByTestId('task-approve-flow')).toBeNull()
    expect(screen.queryByTestId('task-send-back-flow')).toBeNull()
    expect(screen.queryByTestId('task-close-done-elsewhere-flow')).toBeNull()
    expect(screen.queryByTestId('task-cancel-flow')).toBeNull()
  })
})

describe('the board', () => {
  it('closes the selected tasks and names the one the Hub refused', async () => {
    const tasks = ['a', 'b', 'c', 'd'].map((id) => task(id))
    close.mockImplementation((_body, options) =>
      options.onSuccess({
        outcome: 'done_elsewhere',
        commit: 'abc1234',
        closed: [{ id: 'a', status: 'approved' }, { id: 'b', status: 'approved' }, { id: 'c', status: 'approved' }],
        refused: [{ task: 'D', reason: 'it is in a flow or loop', code: 'in_flow' }],
      }),
    )
    render(
      wrap(
        <BoardView
          tasks={tasks}
          agents={[]}
          tallies={{}}
          workingTaskIds={new Set()}
          view="board"
          onViewChange={() => {}}
          folds={{}}
          onFoldsChange={() => {}}
          onOpenTask={() => {}}
          onRetryIntegration={() => {}}
        />,
      ),
    )
    const user = userEvent.setup()
    await user.click(screen.getByTestId('board-select-toggle'))
    for (const id of ['a', 'b', 'c', 'd']) await user.click(screen.getByTestId(`task-select-${id}`))
    await user.selectOptions(screen.getByTestId('close-outcome'), 'done_elsewhere')
    await user.type(screen.getByTestId('close-target'), 'AW-80')
    await user.click(screen.getByTestId('close-submit'))
    expect(close.mock.calls[0][0]).toMatchObject({
      tasks: ['a', 'b', 'c', 'd'],
      outcome: 'done_elsewhere',
      by_task: 'AW-80',
    })
    await waitFor(() => expect(screen.getByTestId('close-refused').textContent).toContain('in a flow'))
    expect(screen.getByTestId('close-refused').textContent).toContain('D')
  })
})
