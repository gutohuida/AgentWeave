import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { TaskWorkView } from '@/components/tasks/TaskViews'
import type { Task, TaskCheckRun } from '@/api/tasks'

/**
 * The view the task drawer actually mounts for a task's checks (FR-11, ac-shown-task): a test
 * quarantine excused has exit code 0 after `quarantine.apply_excuse`, so it must be named as
 * quarantined here, not read as a plain pass.
 */

const TASK: Task = {
  id: 'task-1',
  project_id: 'proj-test',
  title: 'Ship the thing',
  status: 'completed',
  priority: 'medium',
  created_at: '2026-11-18T10:00:00Z',
  updated: '2026-11-18T10:00:00Z',
  divergence_policy: 'surface',
  has_open_divergence: false,
}

const run = (id: string, quarantined: boolean): TaskCheckRun =>
  ({
    id,
    state: 'passed',
    main_sha: 'a'.repeat(40),
    target_shas: [],
    merged_sha: null,
    error: '',
    started_at: null,
    ended_at: null,
    results: [
      {
        name: 'tests',
        exit_code: 0,
        timed_out: false,
        duration_seconds: 4,
        output_tail: '',
        ...(quarantined
          ? { quarantine: { tests: [{ id: 'qt-1', check: 'tests', test: 'tests.test_b::test_flaky', fix_task_id: 'task-fix-2' }], first: { exit_code: 1 } } }
          : {}),
      },
    ],
  }) as unknown as TaskCheckRun

afterEach(cleanup)

describe('the drawer’s checks show a quarantine-excused test', () => {
  it('names it as quarantined, distinct from a plain pass', () => {
    render(<TaskWorkView task={TASK} checks={run('chk-1', true)} />)
    expect(screen.getByText('passed, 1 quarantined')).toBeInTheDocument()
    expect(screen.queryByText(/^passed$/)).toBeNull()
    const row = screen.getByText('tests.test_b::test_flaky').closest('[data-slot="quarantined-test"]')!
    expect(row).toHaveTextContent('quarantined, excused')
    expect(row).toHaveTextContent('task-fix-2')
  })

  it('still reads a clean pass as passed', () => {
    render(<TaskWorkView task={TASK} checks={run('chk-1', false)} />)
    expect(screen.getByText('passed')).toBeInTheDocument()
    expect(document.querySelector('[data-slot="quarantined-test"]')).toBeNull()
  })

  it('shows it in an earlier run too', () => {
    render(<TaskWorkView task={TASK} checks={run('chk-2', false)} earlierChecks={[run('chk-1', true)]} />)
    fireEvent.click(document.querySelector('[data-slot="earlier-runs"]')!)
    expect(screen.getByText('passed, 1 quarantined')).toBeInTheDocument()
  })
})
