import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { Task } from '@/api/tasks'
import { TaskCardCompact } from '@/components/tasks/TaskCardCompact'

/**
 * Two things the board knew and did not say — F14 and F19 from the 2026-08-23 stress-test drive.
 *
 * F14: a run blocked on an unanswered `ask_user` leaves its task at `in_progress` until the run
 * *ends*, so for the whole of the wait the card claimed the work was progressing while the answer
 * sat on the operator's desk.
 *
 * F19: a task gated behind unapproved prerequisites rendered exactly like any ordinary pending
 * card, even though `GET /tasks` already returns each prerequisite and its status.
 *
 * The compact card states each on its one status line (`data-reason` names the fact).
 */

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
  return render(<TaskCardCompact task={task} onOpen={() => {}} />)
}

const status = () => screen.queryByTestId('task-card-status-task-1')

afterEach(cleanup)

describe('a task whose run is waiting on an answer says so (F14)', () => {
  it('carries the waiting treatment without the status having moved', () => {
    const task = makeTask({
      awaiting_answer_reason: 'Waiting on your answer: Which ledger should this report read?',
    })
    renderCard(task)

    expect(status()).toHaveAttribute('data-reason', 'waiting')
    expect(status()).toHaveTextContent('Waiting on you')
    expect(status()).toHaveTextContent('Which ledger should this report read?')
  })

  it('says nothing for an ordinary in-progress task', () => {
    renderCard(makeTask())
    expect(status()).toBeNull()
  })

  it('a parked task still prefers its own recorded reason', () => {
    renderCard(
      makeTask({
        status: 'blocked',
        blocked_reason: 'Waiting on your answer: which ledger?',
        awaiting_answer_reason: 'Waiting on your answer: which ledger?',
      }),
    )
    expect(status()).toHaveTextContent('which ledger?')
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

    const line = status()!
    expect(line).toHaveAttribute('data-reason', 'gated')
    expect(line).toHaveTextContent('Waits on 2 tasks')
    expect(line.getAttribute('title')).toContain('Post the journal entries (under review)')
    expect(line.getAttribute('title')).toContain('Close the period (pending)')
    // Neutral: waiting on unapproved work is the gate behaving correctly, not a problem.
    expect(line).toHaveAttribute('data-tone', 'gated')
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
    // One prerequisite left holding it, so the line names it rather than counting it.
    expect(status()).toHaveTextContent('Waits on Close the period')
    expect(status()!.getAttribute('title')).not.toContain('Post the journal entries')
  })

  it('a rejected prerequisite is red, because it can never clear on its own', () => {
    renderCard(
      makeTask({
        status: 'pending',
        dependency_state: 'gated_on_rejected',
        prerequisites: [{ id: 'task-a', title: 'Post the journal entries', status: 'rejected' }],
      }),
    )
    expect(status()).toHaveAttribute('data-reason', 'gated-on-rejected')
    expect(status()).toHaveTextContent('A prerequisite was rejected')
    expect(status()).toHaveAttribute('data-tone', 'failed')
  })

  it('an ungated task carries no gate', () => {
    renderCard(makeTask({ status: 'pending', dependency_state: null }))
    expect(status()).toBeNull()
  })

  it('a task already running against a regressed prerequisite keeps its own existing flag', () => {
    // `running_on_regressed` is design D8's "flagged, not stopped". F19 must not quietly relabel
    // it as gated — the task is running, not waiting.
    renderCard(
      makeTask({
        dependency_state: 'running_on_regressed',
        prerequisites: [{ id: 'task-a', title: 'Post the journal entries', status: 'rejected' }],
      }),
    )
    expect(status()).toHaveAttribute('data-reason', 'regressed')
  })
})
