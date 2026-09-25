import { describe, it, expect, vi, afterEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import { TaskTransitionHistory } from '@/components/tasks/TaskTransitionHistory'

/**
 * F203: `task_transitions` recorded every accepted move — who asked, from what, under which
 * policy — and nothing could read it. The drives opened sqlite to answer "who moved this?".
 *
 * The distinctions asserted here are the ones the table bothers to record separately: the
 * operator is not a run, and a move the Hub made on a run's behalf (`origin: "runtime"`) is not
 * a move that run chose.
 */

const ROWS = [
  {
    id: 'ttr-1',
    sequence: 1,
    task_id: 'task-1',
    from_status: 'pending',
    to_status: 'assigned',
    actor_kind: 'operator',
    actor_agent: null,
    run_id: null,
    origin: 'actor',
    policy_digest: null,
    created_at: '2026-09-22T10:00:00Z',
  },
  {
    id: 'ttr-2',
    sequence: 2,
    task_id: 'task-1',
    from_status: 'assigned',
    to_status: 'in_progress',
    actor_kind: 'run',
    actor_agent: 'builder',
    run_id: 'run-9',
    origin: 'runtime',
    policy_digest: 'abcdef1234567890',
    created_at: '2026-09-22T10:05:00Z',
  },
]

let rows: typeof ROWS = ROWS

vi.mock('@/api/tasks', () => ({
  useTaskTransitions: () => ({
    data: { transitions: rows },
    isLoading: false,
    isError: false,
  }),
}))

afterEach(() => {
  rows = ROWS
  cleanup()
})

describe('a task’s transition history', () => {
  it('names the operator and the agent separately, because the record does', () => {
    render(<TaskTransitionHistory taskId="task-1" open />)
    const text = screen.getByTestId('task-transitions-task-1').textContent ?? ''

    expect(text).toContain('You')
    expect(text).toContain('builder')
    expect(text).toContain('pending')
    expect(text).toContain('in_progress')
  })

  it('does not credit a run with a move the runtime made on its behalf', () => {
    render(<TaskTransitionHistory taskId="task-1" open />)
    const text = screen.getByTestId('task-transitions-task-1').textContent ?? ''

    expect(text).toContain('was moved for')
  })

  it('shows the policy digest that governed a move, and nothing where none did', () => {
    render(<TaskTransitionHistory taskId="task-1" open />)
    const text = screen.getByTestId('task-transitions-task-1').textContent ?? ''

    expect(text).toContain('abcdef12')
    expect(text).not.toContain('under policy null')
  })

  it('attributes a scheduled job’s move to the flow or loop, whatever order the rows arrive in', () => {
    const job = (id: string, sequence: number, kind: 'flow' | 'loop', name: string) => ({
      ...ROWS[0],
      id,
      sequence,
      origin: 'job',
      job_id: `job-${id}`,
      job_name: name,
      job_kind: kind,
    })
    const flowRow = job('ttr-f', 1, 'flow', 'Ship it')
    const loopRow = job('ttr-l', 2, 'loop', 'Tidy')
    for (const order of [
      [flowRow, loopRow, ROWS[0]],
      [ROWS[0], loopRow, flowRow],
    ]) {
      rows = order as typeof ROWS
      render(<TaskTransitionHistory taskId="task-1" open />)
      const lines = Array.from(
        screen.getByTestId('task-transitions-task-1').querySelectorAll('li'),
      ).map((li) => li.textContent ?? '')
      expect(lines.filter((l) => l.includes('Flow Ship it moved'))).toHaveLength(1)
      expect(lines.filter((l) => l.includes('Loop Tidy moved'))).toHaveLength(1)
      expect(lines.filter((l) => l.includes('You moved'))).toHaveLength(1)
      cleanup()
    }
  })

  it('renders nothing for a task whose history predates the table', () => {
    rows = []
    render(<TaskTransitionHistory taskId="task-1" open />)
    expect(screen.queryByTestId('task-transitions-task-1')).toBeNull()
  })
})
