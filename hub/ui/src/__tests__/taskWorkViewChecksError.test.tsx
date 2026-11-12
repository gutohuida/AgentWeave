import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { TaskWorkView } from '@/components/tasks/TaskViews'
import type { Task } from '@/api/tasks'

/**
 * The Work view's checks when their read fails. Before this, a failed `GET /tasks/{id}/checks`
 * read as "the project's checks have not run on this work yet": a claim about the work made from
 * a failure to read it (the n11 query-error ratchet, `hub/tests/test_surface_ceilings.py`).
 */

const TASK: Task = {
  id: 'task-1',
  project_id: 'proj-test',
  title: 'Ship the thing',
  status: 'completed',
  priority: 'medium',
  created_at: '2026-08-10T10:00:00Z',
  updated: '2026-08-10T10:00:00Z',
  divergence_policy: 'surface',
  has_open_divergence: false,
}

afterEach(cleanup)

describe('TaskWorkView checks', () => {
  it('says the checks could not be read rather than that they have not run', () => {
    render(<TaskWorkView task={TASK} checks={null} checksError="HTTP 500" />)
    expect(screen.getByRole('alert').textContent).toContain('HTTP 500')
    expect(screen.queryByText(/have not run on this work yet/)).toBeNull()
  })

  it('still says the checks have not run when the read succeeded with none', () => {
    render(<TaskWorkView task={TASK} checks={null} checksError={null} />)
    expect(screen.getByText(/have not run on this work yet/)).toBeTruthy()
  })
})
