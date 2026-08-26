/**
 * A skip that names a remediation has to offer a way to perform it.
 *
 * The note used to render every appended attempt with equal weight and no affordance: a stale
 * "Not merged" sat beside the merge that followed it, and a genuinely stuck task offered nothing to
 * press. Approving again cannot re-run a merge, so the reason text was asking for something the
 * operator could not do from here.
 *
 * The one exception is a missing main branch. Retrying there would skip again for the same reason,
 * so that case deliberately shows no button — saving the setting is what re-attempts the merge.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TaskIntegrationNote } from '@/components/tasks/TaskIntegrationNote'
import type { TaskIntegration } from '@/api/tasks'

const retry = vi.fn()
let rows: TaskIntegration[] = []
let pending = false

vi.mock('@/api/tasks', () => ({
  useTaskIntegrations: () => ({ data: { integrations: rows } }),
  useRetryTaskIntegration: () => ({ mutate: retry, isPending: pending, isError: false }),
}))

function row(over: Partial<TaskIntegration>): TaskIntegration {
  return {
    id: `tint-${Math.random().toString(36).slice(2)}`,
    commit_sha: 'abc123def456',
    source_branch: 'agentweave/builder',
    target_branch: 'main',
    outcome: 'skipped',
    reason: 'something',
    rode_along_commits: [],
    mechanism: 'local',
    actor_kind: 'operator',
    actor: 'operator',
    created_at: '2026-08-14T12:00:00Z',
    ...over,
  }
}

describe('TaskIntegrationNote', () => {
  beforeEach(() => {
    retry.mockClear()
    pending = false
    rows = []
  })

  it('offers a retry when the newest attempt did not merge', () => {
    rows = [row({ outcome: 'skipped', reason: 'the checkout has uncommitted changes' })]
    render(<TaskIntegrationNote taskId="task-1" status="approved" />)

    fireEvent.click(screen.getByTestId('task-integration-retry-task-1'))
    expect(retry).toHaveBeenCalledTimes(1)
  })

  it('offers nothing to press once the work is merged', () => {
    rows = [row({ outcome: 'merged', reason: '' })]
    render(<TaskIntegrationNote taskId="task-2" status="approved" />)

    expect(screen.queryByTestId('task-integration-retry-task-2')).toBeNull()
    expect(screen.getByText(/Merged/)).toBeTruthy()
  })

  it('points at the setting rather than a retry when no main branch is set', () => {
    rows = [
      row({
        outcome: 'skipped',
        commit_sha: null,
        target_branch: null,
        reason: "this project has no main branch set — choose one in the project's settings",
      }),
    ]
    render(<TaskIntegrationNote taskId="task-3" status="approved" />)

    expect(screen.queryByTestId('task-integration-retry-task-3')).toBeNull()
    expect(screen.getByText(/no main branch set/)).toBeTruthy()
  })

  it('shows only the newest attempt per target, so a stale skip does not outlive its merge', () => {
    rows = [
      row({ id: 'tint-old', outcome: 'skipped', reason: 'no main branch set' }),
      row({ id: 'tint-new', outcome: 'merged', reason: '' }),
    ]
    render(<TaskIntegrationNote taskId="task-4" status="approved" />)

    expect(screen.queryByText(/Not merged/)).toBeNull()
    expect(screen.getByText(/Merged/)).toBeTruthy()
    // The stale skip is gone, so its "no main branch" wording must not suppress the button either.
    expect(screen.queryByTestId('task-integration-retry-task-4')).toBeNull()
  })

  it('disables the button while a retry is in flight', () => {
    rows = [row({ outcome: 'failed', reason: 'the merge conflicted' })]
    pending = true
    render(<TaskIntegrationNote taskId="task-5" status="approved" />)

    const button = screen.getByTestId('task-integration-retry-task-5') as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.textContent).toContain('Trying')
  })

  it('renders nothing for a task that never reached integration', () => {
    rows = []
    const { container } = render(<TaskIntegrationNote taskId="task-6" status="in_progress" />)
    expect(container.firstChild).toBeNull()
  })

  it('warns when other commits rode along with a merge (F58)', () => {
    rows = [
      row({ id: 'tint-rode-along', outcome: 'merged', reason: '', rode_along_commits: ['a1', 'b2', 'c3'] }),
    ]
    render(<TaskIntegrationNote taskId="task-7" status="approved" />)

    expect(screen.getByTestId('task-integration-rode-along-tint-rode-along')).toBeTruthy()
    expect(screen.getByText(/3 earlier commits on the same branch also landed/)).toBeTruthy()
  })

  it('shows no warning when a merge brought in nothing extra', () => {
    rows = [row({ outcome: 'merged', reason: '', rode_along_commits: [] })]
    render(<TaskIntegrationNote taskId="task-8" status="approved" />)

    expect(screen.queryByText(/also landed with this merge/)).toBeNull()
  })
})
