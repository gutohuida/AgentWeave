import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * A task waiting on the operator, on a board that has no column for it.
 *
 * `blocked` renders as a treatment inside In Progress rather than as a ninth column (R3), which
 * puts the whole burden on the card: if it does not say it is waiting and what for, the operator is
 * back where they were when the card said "in progress" and nothing was happening.
 *
 * The other half is the control. The Hub requires a reason before it will park a task by hand, so a
 * status menu that sent `blocked` on its own would offer a move that then fails — the exact thing
 * the allowed-transitions endpoint exists to prevent.
 */

const updateTask = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({
      data: {
        actor_kind: 'operator',
        transitions: {
          in_progress: ['assigned', 'blocked', 'completed', 'rejected'],
          blocked: ['assigned', 'in_progress', 'rejected'],
        },
      },
    }),
    useUpdateTask: () => ({ mutate: updateTask }),
    useSetDivergenceHandling: () => ({ mutate: vi.fn() }),
    useStartWorkOnTask: () => ({ mutate: vi.fn() }),
  }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'worker' }] }),
}))

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

function renderCard(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCard task={task} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  updateTask.mockReset()
})

afterEach(cleanup)

describe('a waiting task says so on the card', () => {
  it('says it is waiting on the operator, not merely that it is blocked', () => {
    renderCard(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the staging API key' }))

    expect(screen.getByTestId('task-blocked-task-1')).toBeTruthy()
    expect(screen.getByText('Waiting on you')).toBeTruthy()
  })

  it('names what it is waiting for, which is the difference from a bare status', () => {
    renderCard(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the staging API key' }))

    expect(screen.getByText('Waiting on the staging API key')).toBeTruthy()
  })

  it('still reads as waiting when no reason came through', () => {
    renderCard(makeTask({ status: 'blocked' }))

    expect(screen.getByTestId('task-blocked-task-1')).toBeTruthy()
    expect(screen.getByText('Waiting on you')).toBeTruthy()
  })

  it('shows nothing of the sort on a task that is simply running', () => {
    renderCard(makeTask())

    expect(screen.queryByTestId('task-blocked-task-1')).toBeNull()
  })

  it('is not the same signal as stalled', () => {
    /**
     * Opposites: one is an agent that dropped the work, the other an agent that correctly refused
     * to guess. A card showing both at once would be describing two different runs, which is
     * possible — but the waiting banner and the stalled badge must stay distinguishable.
     */
    renderCard(makeTask({ status: 'blocked', has_open_divergence: true, blocked_reason: 'Need a decision' }))

    expect(screen.getByTestId('task-blocked-task-1')).toBeTruthy()
    expect(screen.getByTestId('task-divergence-task-1')).toBeTruthy()
  })
})

describe('parking a task by hand collects the reason first', () => {
  it('does not send the status straight from the menu', async () => {
    renderCard(makeTask())

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))

    // The Hub would refuse this without a reason, so the control must not have sent it.
    expect(updateTask).not.toHaveBeenCalled()
    expect(screen.getByTestId('task-block-reason-task-1')).toBeTruthy()
  })

  it('sends the status and the reason together once given one', async () => {
    renderCard(makeTask())

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))
    await userEvent.type(screen.getByPlaceholderText('e.g. the staging API key'), 'the API key')
    await userEvent.click(screen.getByTestId('task-block-confirm-task-1'))

    expect(updateTask).toHaveBeenCalledTimes(1)
    expect(updateTask.mock.calls[0][0]).toMatchObject({
      id: 'task-1',
      status: 'blocked',
      blocked_reason: 'the API key',
    })
  })

  it('will not send an empty reason', async () => {
    renderCard(makeTask())

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))
    await userEvent.type(screen.getByPlaceholderText('e.g. the staging API key'), '   ')
    await userEvent.click(screen.getByTestId('task-block-confirm-task-1'))

    expect(updateTask).not.toHaveBeenCalled()
  })

  it('releases a waiting task without asking for anything', async () => {
    renderCard(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the key' }))

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-in_progress'))

    expect(updateTask).toHaveBeenCalledTimes(1)
    expect(updateTask.mock.calls[0][0]).toMatchObject({ id: 'task-1', status: 'in_progress' })
    expect(updateTask.mock.calls[0][0].blocked_reason).toBeUndefined()
  })
})
