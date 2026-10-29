import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { Task, TaskChecks } from '@/api/tasks'
import { classify } from '@/lib/notify/classify'
import { overrideOffered, waitsOnChecks, gateBodyOf } from '@/components/tasks/gateRefusal'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * `every-task-can-always-be-moved-on`, FR-9, FR-11, FR-12: the board offers only moves the Hub
 * allows and asks who reviews; a refused landing shows its cause beside the action that clears it;
 * the checks' wait is visible beside Land; a control that cannot act looks it.
 */

const land = vi.fn()
const updateTask = vi.fn()
const decide = vi.fn()
const link = vi.fn()
let moves: { moves: string[]; reviewers?: string[] } = { moves: [] }
let checks: TaskChecks = { configured: true, running: false, runs: [] }
let checksError: Error | null = null

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({ data: { actor_kind: 'operator', transitions: {} } }),
    useTaskMoves: () => ({ data: moves }),
    useUpdateTask: () => ({ mutate: updateTask, isPending: false }),
    useLandTask: () => ({ mutate: land, isPending: false }),
    useDecideEvidencePiece: () => ({ mutate: decide, isPending: false }),
    useLinkTaskRequirements: () => ({ mutate: link, isPending: false }),
    useTaskChecks: () => ({ data: checks, error: checksError }),
    useRerunTaskChecks: () => ({ mutate: vi.fn(), isPending: false }),
    useTaskIntegrationPreview: () => ({ data: null }),
  }
})

function makeTask(status = 'completed'): Task {
  return {
    id: 'task-1',
    project_id: 'proj-test',
    title: 'The spec-page mock',
    status,
    assignee: 'DeveloperOpus',
    priority: 'medium',
    created_at: '2026-10-26T10:00:00Z',
    updated: '2026-10-26T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
  }
}

async function openDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={makeTask()} />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(screen.getByTestId('task-open-task-1'))
  return user
}

const refusal = (detail: Record<string, unknown>) =>
  new ApiError(409, JSON.stringify({ detail: { code: 'gate_unsatisfied', message: 'Refused.', ...detail } }))

beforeEach(() => {
  land.mockReset()
  updateTask.mockReset()
  decide.mockReset()
  link.mockReset()
  moves = { moves: [] }
  checks = { configured: true, running: false, runs: [] }
  checksError = null
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('the board hands a completed task to a reviewer', () => {
  it('offers exactly the route’s moves, and asks who reviews rather than keeping the author', async () => {
    moves = { moves: ['rejected', 'under_review'], reviewers: ['Architect', 'QA'] }
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-status-menu-task-1'))

    expect(screen.getByTestId('task-status-menu-task-1-rejected')).toBeTruthy()
    const review = screen.getByTestId('task-status-menu-task-1-under_review')
    expect(review).toHaveTextContent('Hand to a reviewer')
    expect(screen.queryByText('Move to Under review')).toBeNull()
    expect(screen.queryByTestId('task-status-menu-task-1-approved')).toBeNull()

    await user.click(review)
    expect(updateTask).not.toHaveBeenCalled()
    const picker = screen.getByTestId('task-review-picker-task-1')
    expect(within(picker).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Architect',
      'QA',
      'Cancel',
    ])
    expect(within(picker).queryByText('DeveloperOpus')).toBeNull()

    await user.click(screen.getByTestId('task-review-pick-QA'))
    expect(updateTask.mock.calls[0][0]).toEqual({
      id: 'task-1',
      status: 'under_review',
      assignee: 'QA',
    })
  })

  it('offers no review move at all when the route reports none', async () => {
    moves = { moves: ['rejected'], reviewers: [] }
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-status-menu-task-1'))
    expect(screen.queryByTestId('task-status-menu-task-1-under_review')).toBeNull()
  })
})

describe('a refused landing offers the action that clears it', () => {
  it('names awaiting evidence with Accept and Reject, and Accept decides that piece', async () => {
    land.mockImplementation((_vars, options) =>
      options.onError(
        refusal({
          unaccepted: [{ evidence_id: 'ev-7', identifier: 'FR-11', commit_sha: 'abcdef1234567890' }],
        }),
      ),
    )
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-land-task-1'))

    const piece = await screen.findByTestId('task-landing-awaiting-piece-ev-7')
    expect(piece).toHaveTextContent('FR-11 at abcdef1')
    expect(screen.getByTestId('task-landing-reject-ev-7')).toBeDisabled()
    await user.click(screen.getByTestId('task-landing-accept-ev-7'))
    expect(decide.mock.calls[0][0]).toMatchObject({ id: 'ev-7', decision: 'accepted' })
  })

  it('offers the link for accepted evidence the task does not serve', async () => {
    land.mockImplementation((_vars, options) =>
      options.onError(
        refusal({
          unlanded: [{ branch: 'b', commits: ['c1'] }],
          unlinked: [{ evidence_id: 'ev-9', identifier: 'FR-11', commit_sha: 'c1' }],
        }),
      ),
    )
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-land-task-1'))
    await user.click(await screen.findByTestId('task-landing-link-FR-11'))
    expect(link.mock.calls[0][0]).toEqual({ id: 'task-1', requirement_ids: ['FR-11'] })
  })

  it('says the landing waits while the checks run, and offers no Land anyway', async () => {
    land.mockImplementation((_vars, options) =>
      options.onError(refusal({ checks: [{ state: 'running' }] })),
    )
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-land-task-1'))

    expect(await screen.findByTestId('task-landing-waits-task-1')).toHaveTextContent(
      'Landing waits for the checks',
    )
    expect(screen.queryByTestId('task-land-anyway-task-1')).toBeNull()
  })

  it('offers Land anyway once a check has failed, disabled until a reason is typed', async () => {
    land.mockImplementation((_vars, options) =>
      options.onError(refusal({ checks: [{ state: 'failed', failing: [] }] })),
    )
    const user = await openDrawer()
    await user.click(screen.getByTestId('task-land-task-1'))

    const anyway = await screen.findByTestId('task-land-anyway-task-1')
    expect(anyway).toBeDisabled()
    expect(anyway.getAttribute('title')).toMatch(/why/i)
    expect(anyway.style.opacity).toBe('0.45')
    expect(anyway.style.cursor).toBe('not-allowed')

    await user.click(anyway)
    expect(land).toHaveBeenCalledTimes(1)

    await user.type(screen.getByLabelText('Why land over the failing checks'), 'main fails too')
    expect(screen.getByTestId('task-land-anyway-task-1')).toBeEnabled()
    expect(screen.getByTestId('task-land-anyway-task-1').style.opacity).toBe('')
  })
})

describe('the wait for checks is visible beside Land', () => {
  it('reads the elapsed minutes of the previous run’s duration', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date('2026-10-26T12:08:00Z'))
    checks = {
      configured: true,
      running: true,
      runs: [
        {
          id: 'run-2',
          state: 'running',
          main_sha: 'a',
          target_shas: [],
          merged_sha: null,
          results: [],
          error: '',
          started_at: '2026-10-26T12:00:00Z',
          ended_at: null,
        },
        {
          id: 'run-1',
          state: 'passed',
          main_sha: 'a',
          target_shas: [],
          merged_sha: null,
          results: [],
          error: '',
          started_at: '2026-10-26T11:30:00Z',
          ended_at: '2026-10-26T11:44:00Z',
        },
      ],
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <TaskCardHost task={makeTask()} />
      </QueryClientProvider>,
    )
    screen.getByTestId('task-open-task-1').click()

    const wait = await screen.findByTestId('task-land-wait-task-1')
    // Never a made-up age: before the clock's first reading the label says only that it waits.
    expect(wait.textContent).toMatch(/^Waiting for checks( · running 8 minutes of about 14)?$/)
    await waitFor(() => expect(wait).toHaveTextContent('Waiting for checks · running 8 minutes of about 14'))
    // Beside Land: the same row of the drawer.
    expect(wait.parentElement).toBe(screen.getByTestId('task-land-task-1').parentElement)
  })

  it('says a failed read of the checks instead of showing no run', async () => {
    checksError = new Error('boom')
    await openDrawer()
    expect(await screen.findByTestId('task-land-wait-error-task-1')).toHaveAttribute('role', 'alert')
  })

  it('shows nothing once no run is going', async () => {
    await openDrawer()
    expect(screen.queryByTestId('task-land-wait-task-1')).toBeNull()
  })
})

describe('the refusal body helpers', () => {
  it('waits only on checks alone that have not decided', () => {
    expect(waitsOnChecks({ checks: [{ state: 'running' }] })).toBe(true)
    expect(waitsOnChecks({ checks: [{ state: 'not_run' }] })).toBe(true)
    expect(waitsOnChecks({ checks: [{ state: 'running' }], unaccepted: [{}] })).toBe(false)
    expect(waitsOnChecks({ checks: [{ state: 'failed' }] })).toBe(false)
  })

  it('offers the override only once a check failed, and never over another cause', () => {
    expect(overrideOffered({ checks: [{ state: 'failed' }] })).toBe(true)
    expect(overrideOffered({ checks: [{ state: 'running' }] })).toBe(false)
    expect(overrideOffered({ checks: [{ state: 'failed' }], unlinked: [{}] })).toBe(false)
  })

  it('reads a gate body from a 409 and nothing else', () => {
    expect(gateBodyOf(refusal({}))?.code).toBe('gate_unsatisfied')
    expect(gateBodyOf(new ApiError(403, '{}'))).toBeNull()
    expect(gateBodyOf(new Error('x'))).toBeNull()
  })
})

describe('the operator is notified when the checks finish', () => {
  it('names the task and says whether it can be landed', () => {
    const passed = classify('task_checks_finished', {
      project_id: 'p',
      task_id: 'task-1',
      task_title: 'The spec-page mock',
      state: 'passed',
    })
    expect(passed).toMatchObject({ kind: 'done' })
    expect(passed?.text).toContain('The spec-page mock')
    const failed = classify('task_checks_finished', {
      project_id: 'p',
      task_id: 'task-1',
      task_title: 'The spec-page mock',
      state: 'failed',
    })
    expect(failed).toMatchObject({ kind: 'fail' })
    expect(failed?.text).toContain('The spec-page mock')
  })
})

