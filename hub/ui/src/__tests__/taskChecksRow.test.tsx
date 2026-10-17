import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TaskChecksRow } from '@/components/tasks/TaskChecksRow'
import type { TaskChecks } from '@/api/tasks'

const rerun = vi.fn()
let checks: TaskChecks | undefined

vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  useTaskChecks: () => ({ data: checks }),
  useRerunTaskChecks: () => ({ mutate: rerun, isPending: false, error: null }),
}))

function run(state: TaskChecks['runs'][number]['state'], extra = {}) {
  return {
    id: `chk-${state}`,
    state,
    main_sha: 'a'.repeat(40),
    target_shas: ['b'.repeat(40)],
    merged_sha: null,
    results: [],
    error: '',
    started_at: null,
    ended_at: null,
    ...extra,
  }
}

describe('the task drawer shows the latest check run', () => {
  beforeEach(() => {
    rerun.mockReset()
    checks = undefined
  })

  it('says nothing for a project without checks', () => {
    checks = { configured: false, running: false, runs: [] }
    const { container } = render(<TaskChecksRow taskId="task-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names the failing check and shows its output, newest run first', () => {
    // The route returns newest first; the older passing run must not be what is shown.
    checks = {
      configured: true,
      running: false,
      runs: [
        run('failed', {
          results: [
            { name: 'lint', exit_code: 0, timed_out: false, duration_seconds: 1, output_tail: 'clean' },
            { name: 'tests', exit_code: 1, timed_out: false, duration_seconds: 9, output_tail: 'FAILED test_add' },
          ],
        }),
        run('passed'),
      ],
    }
    render(<TaskChecksRow taskId="task-1" />)
    expect(screen.getByText(/Checks failed/)).toHaveTextContent('tests')
    expect(screen.getByLabelText('Output of tests')).toHaveTextContent('FAILED test_add')
    expect(screen.queryByLabelText('Output of lint')).toBeNull()
  })

  it('shows a running run and offers no re-run while it runs', () => {
    checks = { configured: true, running: true, runs: [run('passed')] }
    render(<TaskChecksRow taskId="task-1" />)
    expect(screen.getByText('Checks running')).toBeInTheDocument()
    expect(screen.getByText('Re-run')).toBeDisabled()
  })

  it('re-runs on request and names an error', () => {
    checks = { configured: true, running: false, runs: [run('error', { error: 'does not merge cleanly' })] }
    render(<TaskChecksRow taskId="task-1" />)
    expect(screen.getByText('does not merge cleanly')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Re-run'))
    expect(rerun).toHaveBeenCalledTimes(1)
  })
})

describe('slice remaining-hidden-data — earlier check runs are in the drawer', () => {
  beforeEach(() => {
    rerun.mockReset()
  })

  it('lists the runs after the newest, in the route’s order, with each check’s exit and duration', () => {
    checks = {
      configured: true,
      running: false,
      runs: [
        run('passed', { id: 'chk-3' }),
        run('failed', {
          id: 'chk-2',
          results: [{ name: 'tests', exit_code: 1, timed_out: false, duration_seconds: 9.5, output_tail: '' }],
        }),
        run('error', { id: 'chk-1', error: 'git worktree failed' }),
      ],
    }
    render(<TaskChecksRow taskId="task-1" />)
    const toggle = screen.getByTestId('task-checks-history-toggle-task-1')
    expect(toggle).toHaveTextContent('Earlier runs (2)')
    fireEvent.click(toggle)
    const rows = screen.getAllByTestId(/^task-check-run-/).map((row) => row.getAttribute('data-testid'))
    expect(rows).toEqual(['task-check-run-chk-2', 'task-check-run-chk-1'])
    expect(screen.getByTestId('task-check-result-chk-2-tests')).toHaveTextContent('tests · exit 1 · 9.5s')
    expect(screen.getByTestId('task-check-run-chk-1')).toHaveTextContent('git worktree failed')
  })

  it('offers no history for a single run', () => {
    checks = { configured: true, running: false, runs: [run('passed')] }
    render(<TaskChecksRow taskId="task-1" />)
    expect(screen.queryByTestId('task-checks-history-toggle-task-1')).toBeNull()
  })
})
