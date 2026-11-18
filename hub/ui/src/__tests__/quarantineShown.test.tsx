import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QuarantineList } from '@/components/overview/QuarantineList'
import { TaskChecksRow } from '@/components/tasks/TaskChecksRow'
import type { NeverQuarantineMark, QuarantinedTest } from '@/api/quarantine'
import type { TaskChecks } from '@/api/tasks'

let checks: TaskChecks | undefined

vi.mock('@/api/tasks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/tasks')>()),
  useTaskChecks: () => ({ data: checks }),
  useRerunTaskChecks: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}))

// The shape and order `GET /checks/quarantine` returns (`quarantine.view`): newest entry first.
const quarantined: QuarantinedTest[] = [
  {
    id: 'qt-new',
    check: 'tests',
    test: 'tests.test_b::test_newer',
    flake_rate: 0.12,
    flips: 3,
    entered_at: '2026-11-18T09:00:00+00:00',
    passes: 4,
    passes_to_exit: 20,
    fix_task_id: 'task-fix-2',
    fix_task: { id: 'task-fix-2', display_id: 'FIX-2', title: 'Fix the flake', status: 'in_progress', assignee: 'Developer' },
  },
  {
    id: 'qt-old',
    check: 'lint',
    test: 'tests.test_a::test_older',
    flake_rate: 0.07,
    flips: 2,
    entered_at: '2026-11-17T09:00:00+00:00',
    passes: 0,
    passes_to_exit: 20,
    fix_task_id: null,
    fix_task: null,
  },
]
const marks: NeverQuarantineMark[] = [
  { id: 'nqm-1', check: 'tests', test: 'tests.test_c::test_guarded', marked_at: '2026-11-18T08:00:00+00:00' },
]

describe('the project overview lists the quarantine (FR-11)', () => {
  const onSetMark = vi.fn()
  const onRemoveMark = vi.fn()
  const onOpenTask = vi.fn()
  beforeEach(() => {
    onSetMark.mockReset()
    onRemoveMark.mockReset()
    onOpenTask.mockReset()
  })

  const renderList = () =>
    render(
      <QuarantineList
        quarantined={quarantined}
        marks={marks}
        onSetMark={onSetMark}
        onRemoveMark={onRemoveMark}
        onOpenTask={onOpenTask}
        now={new Date('2026-11-18T10:00:00Z')}
      />,
    )

  it('shows each test with its check, id, rate on entry, entry time, passes toward exit and fix task, in the route order', () => {
    renderList()
    const rows = within(screen.getByTestId('quarantine-list')).getAllByTestId(/^quarantined-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['quarantined-qt-new', 'quarantined-qt-old'])
    const first = rows[0]
    expect(first).toHaveTextContent('tests.test_b::test_newer')
    expect(first.querySelector('[data-slot="q-check"]')).toHaveTextContent('tests')
    expect(first.querySelector('[data-slot="q-rate"]')).toHaveTextContent('0.12')
    expect(first.querySelector('[data-slot="q-entered"]')).toHaveTextContent('entered')
    expect(first.querySelector('[data-slot="q-passes"]')).toHaveTextContent('4 of 20')
    fireEvent.click(within(first).getByText(/FIX-2/))
    expect(onOpenTask).toHaveBeenCalledWith('task-fix-2')
    expect(rows[1].querySelector('[data-slot="q-fix-task"]')).toHaveTextContent('No fix task')
  })

  it('marks a listed test never to be quarantined, lists the marks, removes one and sets a new one', () => {
    renderList()
    fireEvent.click(within(screen.getByTestId('quarantined-qt-new')).getByText('Never quarantine'))
    expect(onSetMark).toHaveBeenCalledWith('tests', 'tests.test_b::test_newer')

    const marked = screen.getByTestId('never-quarantine-nqm-1')
    expect(marked).toHaveTextContent('tests.test_c::test_guarded')
    fireEvent.click(within(marked).getByText('Remove mark'))
    expect(onRemoveMark).toHaveBeenCalledWith('tests', 'tests.test_c::test_guarded')

    fireEvent.change(screen.getByLabelText('Check name'), { target: { value: 'lint' } })
    fireEvent.change(screen.getByLabelText('Test id'), { target: { value: 'tests.test_x::test_y' } })
    fireEvent.click(screen.getByText('Never quarantine a test'))
    expect(onSetMark).toHaveBeenLastCalledWith('lint', 'tests.test_x::test_y')
  })
})

describe('a task’s checks show a quarantine-excused test (FR-11)', () => {
  it('names it as quarantined, apart from a failure and from known-failing', () => {
    checks = {
      configured: true,
      running: false,
      runs: [
        {
          id: 'chk-1',
          state: 'passed',
          main_sha: 'a'.repeat(40),
          target_shas: ['b'.repeat(40)],
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
              quarantine: {
                tests: [{ id: 'qt-new', check: 'tests', test: 'tests.test_b::test_newer', fix_task_id: 'task-fix-2' }],
                first: { exit_code: 1 },
              },
            },
          ],
        },
      ],
    }
    render(<TaskChecksRow taskId="task-1" />)
    const list = screen.getByTestId('task-checks-quarantined-task-1')
    expect(list).toHaveTextContent('tests.test_b::test_newer')
    expect(list).toHaveTextContent('quarantined')
    expect(screen.getByText('Checks passed')).toBeInTheDocument()
    expect(screen.queryByTestId('task-checks-preexisting-task-1')).toBeNull()
    expect(screen.queryByLabelText('Output of tests')).toBeNull()
  })
})
