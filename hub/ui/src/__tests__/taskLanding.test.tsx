import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { TaskChecks, TaskLanding as Landing } from '@/api/tasks'
import { TaskLanding } from '@/components/tasks/TaskLanding'
import { classify } from '@/lib/notify/classify'

const land = vi.fn()
let checks: TaskChecks | undefined

vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  useTaskChecks: () => ({ data: checks }),
  useLandHeldLanding: () => ({ mutate: land, isPending: false, error: null }),
}))

/** The checks route's `landing`, in the keys and shape `landing_queue.view` returns. */
function landing(state: Landing['state'], extra: Partial<Landing> = {}): Landing {
  return {
    id: 'land-1',
    state,
    kind: 'approval',
    reason: '',
    waits_on: null,
    landed_sha: null,
    override_reason: null,
    batch: null,
    position: null,
    queued_at: '2026-10-27T10:00:00+00:00',
    ...extra,
  }
}

const batch = (extra: Partial<NonNullable<Landing['batch']>> = {}): NonNullable<Landing['batch']> => ({
  id: 'lbat-1',
  state: 'checking',
  task_ids: ['task-1', 'task-2', 'task-3'],
  base_sha: 'a'.repeat(40),
  merged_sha: 'c'.repeat(40),
  check_run_id: 'chk-1',
  seconds: 420,
  previous_seconds: 780,
  override_reason: null,
  override_by: null,
  error: '',
  ...extra,
})

function show(value: Landing) {
  checks = { configured: true, running: false, runs: [], landing: value }
  render(<TaskLanding taskId="task-1" />)
  return screen.getByTestId('task-landing-state-task-1')
}

describe("the drawer shows approved work's landing beside Land", () => {
  beforeEach(() => {
    land.mockReset()
    checks = undefined
  })

  it('says nothing for a Hub or task with no landing', () => {
    checks = { configured: true, running: false, runs: [] }
    const { container } = render(<TaskLanding taskId="task-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a queued landing with its place in the queue', () => {
    expect(show(landing('queued', { position: 3 }))).toHaveTextContent('Queued to land · #3 in the queue')
  })

  it('shows a checking batch with how long it has run and how long the previous one took', () => {
    const line = show(landing('checking', { batch: batch() }))
    expect(line).toHaveTextContent('Checking with 3 tasks')
    expect(line).toHaveTextContent('running 7 min')
    expect(line).toHaveTextContent('the previous batch took 13 min')
  })

  it('shows what a held landing waits on, and lands a batch held on main with one reason', () => {
    const reason = 'the batch\'s checks fail, and they fail on main too, so the failure is not this work\'s'
    const line = show(landing('held', { reason, batch: batch({ state: 'held' }) }))
    expect(line).toHaveTextContent('Held for you')
    expect(screen.getByText(reason)).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('task-landing-reason-task-1'), {
      target: { value: 'main is red; fixed separately' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Land batch' }))
    expect(land).toHaveBeenCalledWith('main is red; fixed separately')
  })

  it('names the prerequisite a held landing waits for, with no override offered', () => {
    expect(show(landing('held', { waits_on: 'task-0', reason: 'built on task-0' }))).toHaveTextContent(
      'waits for task-0 to land first',
    )
    expect(screen.queryByRole('button', { name: 'Land batch' })).toBeNull()
  })

  it('shows the commit a landed task reached main at', () => {
    expect(show(landing('landed', { landed_sha: 'd'.repeat(40) }))).toHaveTextContent(
      'Landed on main at dddddddd',
    )
  })

  it('shows why a task was sent back, with the failing output', () => {
    const report = 'Landing batch lbat-1 found that task task-1\'s work ... FAILED test_suite.py::test_no_marker'
    expect(show(landing('sent_back', { reason: report }))).toHaveTextContent('Sent back by its landing batch')
    expect(screen.getByLabelText('Why it did not land')).toHaveTextContent('test_no_marker')
  })
})

describe('the operator is told when a batch lands or sends a task back', () => {
  const payload = (state: string) => ({
    project_id: 'proj-1',
    task_id: 'task-1',
    task_title: 'Add the ledger',
    landing_id: 'land-1',
    state,
    batch_id: 'lbat-1',
    reason: '',
  })

  it('notifies a landing, a send-back and a hold, and nothing for the queue moving', () => {
    expect(classify('task_landing_changed', payload('landed'))?.text).toBe('Add the ledger landed on main')
    expect(classify('task_landing_changed', payload('sent_back'))?.kind).toBe('fail')
    expect(classify('task_landing_changed', payload('held'))?.kind).toBe('ask')
    expect(classify('task_landing_changed', payload('checking'))).toBeNull()
  })
})
