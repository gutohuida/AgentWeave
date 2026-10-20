import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import type { Task } from '@/api/tasks'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'
import { cardStatus } from '@/lib/taskCardStatus'

/**
 * The compact board card states, on its one status line, every fact the old card drew as a badge
 * of its own (`TaskCard`: blocked, proceeded, divergence, gated, regressed, live, not merged), in
 * urgency order, and keeps the one action reached for while scanning: Start work.
 */

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Ship the thing',
    status: 'in_progress',
    priority: 'medium',
    assignee: 'worker',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

afterEach(cleanup)

describe('the status line', () => {
  it('coalesces a blocked task and an open ask into one wait (F14)', () => {
    const status = cardStatus(makeTask({ status: 'blocked', blocked_reason: 'Which port?', awaiting_answer_reason: 'Which port?' }))
    expect(status?.reason).toBe('waiting')
    expect(status?.text).toBe('Waiting on you · Which port?')
  })

  it('says a task waits even when it parked without a reason', () => {
    expect(cardStatus(makeTask({ status: 'blocked' }))?.reason).toBe('waiting')
  })

  it('names a decision taken without the operator (F60), and keeps it as history once approved', () => {
    expect(cardStatus(makeTask({ proceeded_without_answer_reason: 'Chose 8080' }))?.reason).toBe('proceeded')
    expect(cardStatus(makeTask({ status: 'approved', proceeded_without_answer_reason: 'Chose 8080' }))?.reason).toBe(
      'decided-without-you',
    )
  })

  it('names a dropped run, a regressed prerequisite and both gates', () => {
    expect(cardStatus(makeTask({ has_open_divergence: true }))?.reason).toBe('divergence')
    expect(cardStatus(makeTask({ dependency_state: 'running_on_regressed' }))?.reason).toBe('regressed')
    const gated = cardStatus(
      makeTask({
        status: 'pending',
        dependency_state: 'gated',
        prerequisites: [{ id: 'p1', title: 'Lay the pipe', status: 'in_progress' }],
      }),
    )
    expect(gated?.reason).toBe('gated')
    expect(gated?.text).toBe('Waits on Lay the pipe')
    expect(gated?.detail).toContain('Lay the pipe (in progress)')
    const onRejected = cardStatus(makeTask({ status: 'pending', dependency_state: 'gated_on_rejected' }))
    expect(onRejected?.reason).toBe('gated-on-rejected')
    expect(onRejected?.tone).toBe('failed')
  })

  it('says an approved task did not merge, and offers Retry', () => {
    const onRetry = vi.fn()
    render(
      <TaskCardCompact
        task={makeTask({
          status: 'approved',
          latest_integration: { outcome: 'skipped', reason: 'the checkout has local changes', commit_sha: null, target_branch: 'main', created_at: '2026-08-10T10:00:00Z' },
        })}
        onOpen={vi.fn()}
        onRetryIntegration={onRetry}
      />,
    )
    const line = screen.getByTestId('task-card-status-task-1')
    expect(line).toHaveAttribute('data-reason', 'not-merged')
    expect(line).toHaveAttribute('title', 'The checkout has local changes.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledWith('task-1')
  })

  it('puts the wait ahead of live work', () => {
    expect(cardStatus(makeTask({ awaiting_answer_reason: 'Which port?' }), true)?.reason).toBe('waiting')
    expect(cardStatus(makeTask(), true)?.reason).toBe('working')
  })
})

describe('start work', () => {
  it('starts the chosen agent on the task from the card', async () => {
    const onStartWork = vi.fn()
    render(<TaskCardCompact task={makeTask()} onOpen={vi.fn()} startAgents={['worker', 'qa']} onStartWork={onStartWork} />)

    await userEvent.click(screen.getByRole('button', { name: 'Start work on Ship the thing' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: 'Start qa on this' }))
    expect(onStartWork).toHaveBeenCalledWith('task-1', 'qa')
  })

  it('offers no menu without agents to start', () => {
    render(<TaskCardCompact task={makeTask()} onOpen={vi.fn()} startAgents={[]} onStartWork={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Start work on/ })).toBeNull()
  })
})
