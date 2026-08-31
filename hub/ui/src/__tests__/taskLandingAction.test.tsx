import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { Task } from '@/api/tasks'
import { TaskCardHost } from './testUtils/TaskCardHost'

/**
 * "Land it" — F163's affordance (`approval-waits-for-the-turn-to-end`, task 6.4).
 *
 * The drive that found F163 had a loop's completed task and three calls to make, two of which
 * begin as refusals. The Hub now composes them; this is where the operator reaches that, and the
 * two things worth pinning are that it appears **only** on completed work and that its refusal is
 * rendered where a refused status move already is — the live-turn one especially, which is F162
 * arriving through this door and is the only refusal an operator will meet in normal use.
 */

const OPERATOR_TRANSITIONS: Record<string, string[]> = {
  pending: ['assigned', 'in_progress', 'rejected'],
  in_progress: ['assigned', 'completed', 'rejected'],
  completed: ['rejected', 'under_review'],
  under_review: ['approved', 'rejected', 'revision_needed'],
  approved: ['revision_needed'],
}

const land = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({
      data: { actor_kind: 'operator', transitions: OPERATOR_TRANSITIONS },
    }),
    useUpdateTask: () => ({ mutate: vi.fn() }),
    useLandTask: () => ({ mutate: land, isPending: false }),
    // The drawer asks what approving would write; irrelevant here and it would otherwise fetch.
    useTaskIntegrationPreview: () => ({ data: null }),
  }
})

function makeTask(status: string): Task {
  return {
    id: `task-${status}`,
    project_id: 'proj-test',
    title: `A ${status} task`,
    status,
    assignee: 'builder',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
  }
}

async function openDrawer(status: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TaskCardHost task={makeTask(status)} />
    </QueryClientProvider>,
  )
  const user = userEvent.setup()
  await user.click(screen.getByTestId(`task-open-task-${status}`))
  return user
}

/** The Hub's live-turn refusal, exactly as `GateRefusal.to_dict()` sends it. */
function liveTurnRefusal(): ApiError {
  return new ApiError(
    409,
    JSON.stringify({
      detail: {
        code: 'gate_unsatisfied',
        message:
          'Cannot approve task tsk-1 yet: builder still has a turn running on it. The work it ' +
          'has done is not committed until that turn ends. This clears itself when the turn ends.',
        unfinished: [{ agent: 'builder', run_id: 'run-1' }],
      },
    }),
  )
}

beforeEach(() => {
  land.mockReset()
})

afterEach(cleanup)

describe('the landing action', () => {
  it('is offered on completed work', async () => {
    await openDrawer('completed')
    expect(screen.getByTestId('task-land-task-completed')).toBeTruthy()
  })

  it.each(['pending', 'in_progress', 'under_review', 'approved'])(
    'is not offered from %s',
    async (status) => {
      await openDrawer(status)
      expect(screen.queryByTestId(`task-land-task-${status}`)).toBeNull()
    },
  )

  it('issues one call rather than a status change', async () => {
    const user = await openDrawer('completed')
    await user.click(screen.getByTestId('task-land-task-completed'))

    expect(land).toHaveBeenCalledTimes(1)
    expect(land.mock.calls[0][0]).toEqual({ id: 'task-completed' })
  })

  it("renders the Hub's refusal where a refused move renders", async () => {
    land.mockImplementation((_vars, options) => options.onError(liveTurnRefusal()))
    const user = await openDrawer('completed')
    await user.click(screen.getByTestId('task-land-task-completed'))

    await waitFor(() => {
      expect(screen.getByTestId('task-status-refusal-task-completed').textContent).toContain(
        'still has a turn running on it',
      )
    })
  })

  it('does not fall back to a generic sentence when the refusal is structured', async () => {
    // The whole point of `readableApiError`'s object branch: a gate refusal carries its sentence
    // inside `detail.message`, and a caller that read only `detail` as a string would show its own
    // fallback instead — which is how a refusal that says exactly what to do becomes "refused".
    land.mockImplementation((_vars, options) => options.onError(liveTurnRefusal()))
    const user = await openDrawer('completed')
    await user.click(screen.getByTestId('task-land-task-completed'))

    await waitFor(() => {
      expect(screen.getByTestId('task-status-refusal-task-completed').textContent).not.toContain(
        'The Hub refused this landing.',
      )
    })
  })
})
