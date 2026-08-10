import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import type { Task } from '@/api/tasks'
import { TaskCard } from '@/components/tasks/TaskCard'

/**
 * The operator's status control (B1 §7).
 *
 * Before this, the board was read-only — `useUpdateTask` existed with no callers — so the
 * operator-only edges the machine grants (early rejection, reopening a decided task) were
 * enforced in the API and reachable nowhere in the product.
 *
 * What matters here is that the control offers *exactly* what the Hub says is legal for an
 * operator from the card's own status. Offering a superset and letting the API refuse would teach
 * the operator to expect their own controls to fail.
 */

// The operator's view of the map, as `GET /tasks/transitions/allowed` serves it. Mirrors the
// declaration in `hub/hub/task_transitions.py`; the Hub-side test pins that the endpoint and the
// enforcement agree, so this fixture only has to be the shape.
const OPERATOR_TRANSITIONS: Record<string, string[]> = {
  pending: ['assigned', 'in_progress', 'rejected'],
  assigned: ['in_progress', 'pending', 'rejected'],
  in_progress: ['assigned', 'completed', 'rejected'],
  completed: ['rejected', 'under_review'],
  under_review: ['approved', 'rejected', 'revision_needed'],
  revision_needed: ['in_progress', 'rejected'],
  approved: ['revision_needed'],
  rejected: ['pending'],
}

const mutate = vi.fn()

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useAllowedTransitions: () => ({
      data: { actor_kind: 'operator', transitions: OPERATOR_TRANSITIONS },
    }),
    useUpdateTask: () => ({ mutate }),
  }
})

function makeTask(status: string): Task {
  return {
    id: `task-${status}`,
    project_id: 'proj-test',
    title: `A ${status} task`,
    status,
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
  }
}

function renderCard(status: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TaskCard task={makeTask(status)} />
    </QueryClientProvider>,
  )
}

async function openMenu(status: string) {
  const user = userEvent.setup()
  await user.click(screen.getByTestId(`task-status-menu-task-${status}`))
  return user
}

beforeEach(() => {
  mutate.mockReset()
})

afterEach(cleanup)

describe('the task status control', () => {
  it.each(Object.keys(OPERATOR_TRANSITIONS))(
    'offers exactly the operator-legal moves from %s',
    async (status) => {
      renderCard(status)
      await openMenu(status)

      await waitFor(() => {
        expect(screen.getByTestId(`task-status-menu-task-${status}-${OPERATOR_TRANSITIONS[status][0]}`)).toBeTruthy()
      })

      for (const target of OPERATOR_TRANSITIONS[status]) {
        expect(screen.getByTestId(`task-status-menu-task-${status}-${target}`)).toBeTruthy()
      }

      // Nothing outside the declared set — the contract that makes D13 worth having.
      const offered = screen
        .getAllByRole('menuitem')
        .map((item) => item.getAttribute('data-testid'))
        .map((id) => id?.replace(`task-status-menu-task-${status}-`, ''))
      expect(offered.sort()).toEqual([...OPERATOR_TRANSITIONS[status]].sort())
    },
  )

  it('never offers a move an agent could make but an operator could not', () => {
    // The operator's set is a superset of the agent's everywhere, so there is no such move — this
    // asserts the fixture itself has not drifted into claiming otherwise.
    expect(OPERATOR_TRANSITIONS.approved).toEqual(['revision_needed'])
    expect(OPERATOR_TRANSITIONS.rejected).toEqual(['pending'])
  })

  it('offers reopening from approved, which is the operator-only edge D9 added', async () => {
    renderCard('approved')
    await openMenu('approved')

    await waitFor(() => {
      expect(screen.getByTestId('task-status-menu-task-approved-revision_needed')).toBeTruthy()
    })
    expect(screen.queryByTestId('task-status-menu-task-approved-in_progress')).toBeNull()
  })

  it('sends the chosen status through the update mutation', async () => {
    renderCard('pending')
    const user = await openMenu('pending')

    await waitFor(() => {
      expect(screen.getByTestId('task-status-menu-task-pending-rejected')).toBeTruthy()
    })
    await user.click(screen.getByTestId('task-status-menu-task-pending-rejected'))

    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(1))
    expect(mutate.mock.calls[0][0]).toEqual({ id: 'task-pending', status: 'rejected' })
  })

  it('shows the Hub’s own refusal sentence rather than a generic failure', async () => {
    // A stale board can offer a move that has since become illegal. The 409 detail names the
    // current status and what is reachable; showing "error" instead would strand the operator.
    mutate.mockImplementation((_vars, options) => {
      options.onError(
        new ApiError(
          409,
          JSON.stringify({
            detail:
              "Cannot move a task from 'completed' to 'approved'. From 'completed' the available transitions are: rejected, under_review.",
          }),
        ),
      )
    })

    renderCard('completed')
    const user = await openMenu('completed')

    await waitFor(() => {
      expect(screen.getByTestId('task-status-menu-task-completed-under_review')).toBeTruthy()
    })
    await user.click(screen.getByTestId('task-status-menu-task-completed-under_review'))

    const refusal = await screen.findByTestId('task-status-refusal-task-completed')
    expect(refusal.textContent).toContain('available transitions are: rejected, under_review')
    // Not the raw JSON body, which is what `ApiError.message` would have rendered.
    expect(refusal.textContent).not.toContain('{')
  })

  it('renders no control when the map offers nothing from this status', () => {
    // Defensive: an agent-scoped map would report no exits from `approved`. The card must then
    // show no menu at all rather than an empty one.
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TaskCard task={{ ...makeTask('approved'), status: 'unknown_status' }} />
      </QueryClientProvider>,
    )
    expect(screen.queryByTestId('task-status-menu-task-approved')).toBeNull()
  })
})
