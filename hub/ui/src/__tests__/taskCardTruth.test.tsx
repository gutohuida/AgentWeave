import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * Two things the board knew and did not say — F14 and F19 from the 2026-08-23 stress-test drive.
 *
 * F14: a run blocked on an unanswered `ask_user` leaves its task at `in_progress` until the run
 * *ends*, so for the whole of the wait — which is the entire point of asking — the card claimed the
 * work was progressing while the answer sat on the operator's desk.
 *
 * F19: a task gated behind unapproved prerequisites rendered exactly like any ordinary pending
 * card, even though `GET /tasks` already returns each prerequisite and its status.
 */

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useStartWorkOnTask: () => ({ mutate: vi.fn() }) }
})

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [] }),
}))

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'Add a trial-balance report',
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
  return render(
    <QueryClientProvider client={client}>
      <TaskCard task={task} onOpen={() => {}} />
    </QueryClientProvider>,
  )
}

afterEach(cleanup)

describe('a task whose run is waiting on an answer says so (F14)', () => {
  it('carries the waiting treatment without the status having moved', () => {
    renderCard(
      makeTask({
        awaiting_answer_reason: 'Waiting on your answer: Which ledger should this report read?',
      }),
    )

    const note = screen.getByTestId('task-blocked-task-1')
    expect(note).toHaveTextContent('Waiting on you')
    expect(note).toHaveTextContent('Which ledger should this report read?')
    // The status is deliberately untouched — F14 is a reporting fix, not a transition.
    expect(screen.getByText('in progress')).toBeInTheDocument()
  })

  it('says nothing for an ordinary in-progress task', () => {
    renderCard(makeTask())
    expect(screen.queryByTestId('task-blocked-task-1')).toBeNull()
  })

  it('a parked task still prefers its own recorded reason', () => {
    // Both fields are populated once the run ends and `block_task_for_question` writes
    // `blocked_reason`. The stored one is the record; the derived one restates it.
    renderCard(
      makeTask({
        status: 'blocked',
        blocked_reason: 'Waiting on your answer: which ledger?',
        awaiting_answer_reason: 'Waiting on your answer: which ledger?',
      }),
    )
    expect(screen.getByTestId('task-blocked-task-1')).toHaveTextContent('which ledger?')
  })
})

describe('a gated task is marked as gated (F19)', () => {
  it('names how many prerequisites are holding it, and which, in the title', () => {
    renderCard(
      makeTask({
        status: 'pending',
        dependency_state: 'gated',
        prerequisites: [
          { id: 'task-a', title: 'Post the journal entries', status: 'under_review' },
          { id: 'task-b', title: 'Close the period', status: 'pending' },
        ],
      }),
    )

    const badge = screen.getByTestId('task-gated-task-1')
    expect(badge).toHaveTextContent('Waiting on 2 tasks')
    expect(badge.getAttribute('title')).toContain('Post the journal entries (under review)')
    expect(badge.getAttribute('title')).toContain('Close the period (pending)')
    // Neutral: waiting on unapproved work is the gate behaving correctly, not a problem.
    expect(badge.getAttribute('style')).not.toContain('--red')
  })

  it('an approved prerequisite is not counted as holding anything', () => {
    renderCard(
      makeTask({
        status: 'pending',
        dependency_state: 'gated',
        prerequisites: [
          { id: 'task-a', title: 'Post the journal entries', status: 'approved' },
          { id: 'task-b', title: 'Close the period', status: 'pending' },
        ],
      }),
    )
    expect(screen.getByTestId('task-gated-task-1')).toHaveTextContent('Waiting on 1 task')
  })

  it('a rejected prerequisite is red, because it can never clear on its own', () => {
    renderCard(
      makeTask({
        status: 'pending',
        dependency_state: 'gated_on_rejected',
        prerequisites: [{ id: 'task-a', title: 'Post the journal entries', status: 'rejected' }],
      }),
    )
    const badge = screen.getByTestId('task-gated-task-1')
    expect(badge).toHaveTextContent('Prerequisite rejected')
    expect(badge.getAttribute('style')).toContain('--red')
  })

  it('an ungated task carries no badge', () => {
    renderCard(makeTask({ status: 'pending', dependency_state: null }))
    expect(screen.queryByTestId('task-gated-task-1')).toBeNull()
  })

  it('a task already running against a regressed prerequisite keeps its own existing badge', () => {
    // `running_on_regressed` is design D8's "flagged, not stopped" and has said so since task 8.9.
    // F19 must not quietly relabel it as gated — the task is running, not waiting.
    renderCard(
      makeTask({
        dependency_state: 'running_on_regressed',
        prerequisites: [{ id: 'task-a', title: 'Post the journal entries', status: 'rejected' }],
      }),
    )
    expect(screen.queryByTestId('task-gated-task-1')).toBeNull()
    expect(screen.getByTestId('task-dependency-regressed-task-1')).toBeInTheDocument()
  })
})
