import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * A task waiting on the operator, on a board that has no column for it.
 *
 * `blocked` renders as a treatment inside In Progress rather than as a ninth column (R3), which
 * puts the whole burden on the card: if it does not say it is waiting and what for, the operator is
 * back where they were when the card said "in progress" and nothing was happening. The compact
 * card says it on its status line (`data-reason="waiting"`).
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
  render(<TaskCardCompact task={task} onOpen={() => {}} />)
}

const status = () => screen.queryByTestId('task-card-status-task-1')

// The status-transition menu, the blocking-reason input and the decision record live in the
// drawer (F5, `design.md` D8) — opened the way the operator would, by clicking the card.
async function renderCardOpen(task: Task) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={task} />
    </QueryClientProvider>,
  )
  await userEvent.click(screen.getByTestId(`task-open-${task.id}`))
}

beforeEach(() => {
  updateTask.mockReset()
})

afterEach(cleanup)

describe('a waiting task says so on the card', () => {
  it('says it is waiting on the operator, not merely that it is blocked', () => {
    renderCard(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the staging API key' }))

    expect(status()).toHaveAttribute('data-reason', 'waiting')
    expect(status()).toHaveTextContent('Waiting on you')
  })

  it('names what it is waiting for, which is the difference from a bare status', () => {
    renderCard(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the staging API key' }))

    expect(status()).toHaveTextContent('Waiting on the staging API key')
  })

  it('still reads as waiting when no reason came through', () => {
    renderCard(makeTask({ status: 'blocked' }))

    expect(status()).toHaveAttribute('data-reason', 'waiting')
    expect(status()).toHaveTextContent('Waiting on you')
  })

  it('shows nothing of the sort on a task that is simply running', () => {
    renderCard(makeTask())

    expect(status()).toBeNull()
  })

  it('renders one wait, not two, when the task is both parked and reporting a wait', () => {
    /**
     * Ask-time parking (F14) makes a task carry `blocked` *and* `awaiting_answer_reason` at the
     * same moment. A later edit that split them would tell the operator they owe two answers when
     * they owe one.
     */
    renderCard(
      makeTask({
        status: 'blocked',
        blocked_reason: 'Waiting on your answer: which colour?',
        awaiting_answer_reason: 'Waiting on your answer: which colour?',
      }),
    )

    expect(screen.getAllByTestId('task-card-status-task-1')).toHaveLength(1)
    expect(status()!.textContent!.split('which colour?')).toHaveLength(2)
  })

  it('is not the same signal as stalled', () => {
    /**
     * Opposites: one is an agent that dropped the work, the other an agent that correctly refused
     * to guess. The waiting line and the stalled line must stay distinguishable — and with one
     * status line, the live ask the operator can still answer is the one stated.
     */
    renderCard(makeTask({ status: 'blocked', has_open_divergence: true, blocked_reason: 'Need a decision' }))
    expect(status()).toHaveAttribute('data-reason', 'waiting')
    expect(status()).toHaveAttribute('data-tone', 'waiting')
    cleanup()

    renderCard(makeTask({ has_open_divergence: true }))
    expect(status()).toHaveAttribute('data-reason', 'divergence')
    expect(status()).toHaveAttribute('data-tone', 'failed')
  })
})

describe('parking a task by hand collects the reason first', () => {
  it('does not send the status straight from the menu', async () => {
    await renderCardOpen(makeTask())

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))

    // The Hub would refuse this without a reason, so the control must not have sent it.
    expect(updateTask).not.toHaveBeenCalled()
    expect(screen.getByTestId('task-block-reason-task-1')).toBeTruthy()
  })

  it('sends the status and the reason together once given one', async () => {
    await renderCardOpen(makeTask())

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
    await renderCardOpen(makeTask())

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-blocked'))
    await userEvent.type(screen.getByPlaceholderText('e.g. the staging API key'), '   ')
    await userEvent.click(screen.getByTestId('task-block-confirm-task-1'))

    expect(updateTask).not.toHaveBeenCalled()
  })

  it('releases a waiting task without asking for anything', async () => {
    await renderCardOpen(makeTask({ status: 'blocked', blocked_reason: 'Waiting on the key' }))

    await userEvent.click(screen.getByTestId('task-status-menu-task-1'))
    await userEvent.click(screen.getByTestId('task-status-menu-task-1-in_progress'))

    expect(updateTask).toHaveBeenCalledTimes(1)
    expect(updateTask.mock.calls[0][0]).toMatchObject({ id: 'task-1', status: 'in_progress' })
    expect(updateTask.mock.calls[0][0].blocked_reason).toBeUndefined()
  })
})

describe('a task that went ahead without your answer says so, permanently', () => {
  it('renders the record on a completed task', async () => {
    /**
     * F60: the agent asked, waited out its deadline, chose for itself and finished the work. The
     * card names the fact, with the decision in its title; the drawer carries the record in full.
     */
    const task = makeTask({
      status: 'completed',
      proceeded_without_answer_reason: 'Proceeded without your answer: which colour?',
    })
    await renderCardOpen(task)

    expect(status()).toHaveAttribute('data-reason', 'proceeded')
    expect(status()).toHaveAttribute('title', 'Proceeded without your answer: which colour?')
    const record = screen.getByTestId('task-proceeded-detail-task-1')
    expect(record).toHaveTextContent('Decided without you')
    expect(record).toHaveTextContent('Proceeded without your answer: which colour?')
  })

  it('shows nothing of the sort on a task whose question was answered', async () => {
    await renderCardOpen(makeTask({ status: 'completed' }))

    expect(status()).toBeNull()
    expect(screen.queryByTestId('task-proceeded-detail-task-1')).toBeNull()
  })

  it('is drawn distinctly from a live wait, because they call for opposite things', async () => {
    /**
     * A wait is an ask the operator can still answer; this is a decision already taken. The card's
     * one line states the live ask; the drawer still carries the decision record beside it.
     */
    await renderCardOpen(
      makeTask({
        status: 'blocked',
        blocked_reason: 'Waiting on your answer: which database?',
        proceeded_without_answer_reason: 'Proceeded without your answer: which colour?',
      }),
    )

    expect(status()).toHaveAttribute('data-reason', 'waiting')
    expect(status()).toHaveTextContent('which database?')
    expect(screen.getByTestId('task-proceeded-detail-task-1')).toHaveTextContent('which colour?')
  })
})

describe('an approved task keeps the record as one line of history (fix-D14, F659)', () => {
  it('collapses the block once the task is approved', async () => {
    await renderCardOpen(
      makeTask({
        status: 'approved',
        proceeded_without_answer_reason: 'Proceeded without your answer: which colour?',
      }),
    )

    // On the card: quiet history, not the amber "went ahead" line that asks for attention.
    expect(status()).toHaveAttribute('data-reason', 'decided-without-you')
    expect(status()).toHaveAttribute('data-tone', 'decided')
    expect(status()).toHaveTextContent('Decided without you earlier')
    // In the drawer: one line, not the block.
    expect(screen.queryByTestId('task-proceeded-detail-task-1')).toBeNull()
    const line = screen.getByTestId('task-proceeded-history-detail-task-1')
    expect(line.textContent).toContain('Earlier, decided without you')
    expect(line.textContent).toContain('which colour?')
  })

  it('keeps the block on a task not yet approved', async () => {
    await renderCardOpen(
      makeTask({
        status: 'in_progress',
        proceeded_without_answer_reason: 'Proceeded without your answer: which colour?',
      }),
    )

    expect(status()).toHaveAttribute('data-reason', 'proceeded')
    expect(screen.getByTestId('task-proceeded-detail-task-1')).toBeTruthy()
    expect(screen.queryByTestId('task-proceeded-history-detail-task-1')).toBeNull()
  })
})
