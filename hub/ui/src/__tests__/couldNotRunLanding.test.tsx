import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TaskLanding } from '@/components/tasks/TaskLanding'
import type { TaskChecks } from '@/api/tasks'

let checks: TaskChecks | undefined

vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  useTaskChecks: () => ({ data: checks }),
}))

describe('the landing record names a check that could not run (FR-8)', () => {
  it('shows could not run with the program and the link failure, not passed', () => {
    checks = {
      configured: true,
      running: false,
      runs: [],
      landing: {
        id: 'land-1',
        state: 'not_landed',
        kind: 'approval',
        reason: '',
        waits_on: null,
        landed_sha: null,
        override_reason: null,
        batch: {
          id: 'batch-1',
          state: 'failed',
          task_ids: ['task-1'],
          base_sha: 'a'.repeat(40),
          merged_sha: null,
          check_run_id: null,
          seconds: 3,
          previous_seconds: null,
          override_reason: null,
          override_by: null,
          error: '',
          could_not_run: [
            {
              name: 'hub-ui',
              missing_program: 'eslint',
              dependency_link_failures: [{ name: 'node_modules', reason: 'symlink refused' }],
            },
          ],
        },
        position: null,
        queued_at: null,
      },
    }
    render(<TaskLanding taskId="task-1" />)
    const said = screen.getByTestId('task-landing-could-not-run-task-1')
    expect(said).toHaveTextContent('hub-ui could not run: eslint was not found')
    expect(said).toHaveTextContent('node_modules: symlink refused')
    expect(screen.queryByText(/passed/i)).toBeNull()
  })

  it('names the check on a landing queued again with no batch, the shape the route returns', () => {
    checks = {
      configured: true,
      running: false,
      runs: [],
      landing: {
        id: 'land-1',
        state: 'queued',
        kind: 'approval',
        reason: '',
        waits_on: null,
        landed_sha: null,
        override_reason: null,
        batch: null,
        could_not_run: [{ name: 'hub-ui', missing_program: 'eslint', dependency_link_failures: [] }],
        position: 1,
        queued_at: null,
      },
    }
    render(<TaskLanding taskId="task-1" />)
    expect(screen.getByTestId('task-landing-could-not-run-task-1')).toHaveTextContent(
      'hub-ui could not run: eslint was not found',
    )
  })
})
