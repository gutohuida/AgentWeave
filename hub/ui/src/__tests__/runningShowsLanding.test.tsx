import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import type { LoopSummary } from '@/api/jobs'
import type { ProjectBuildRow } from '@/api/projectBuilds'
import type { Task } from '@/api/tasks'
import { RunningTab } from '@/components/panel/RunningTab'
import { runningItems } from '@/components/panel/runningModel'
import { TaskCard } from '@/components/tasks/TaskCard'

/* Work is done when it has landed on main, not when it is approved
 * (`work-is-done-when-it-has-landed-on-master-not-when-it-is-approved`, FR-4, FR-6, FR-7). The build
 * row below is `GET /projects/{id}/project/builds`'s row as the route returned it in the Hub's own
 * acceptance drive (`hub/tests/test_work_is_done_when_it_has_landed.py::test_ac_drive_…`): the first
 * task landed, the second sent back by its landing, the build still running. */

afterEach(cleanup)

const NOW = new Date('2026-11-13T18:00:00Z')

const REASON =
  "Landing batch lbat-e6c0931a8172 found that task task-e8907d605351's work, landed on task-59525fb8fdb5 in the same batch, makes the project's check `hub-tests` fail (check run chk-8e2b4ae6528b). It goes back to its author; the rest of the batch lands without it.\n\nFAILED tests/test_bad.py::test_no_bad_file"

function routeRow(overrides: Partial<ProjectBuildRow> = {}): ProjectBuildRow {
  return {
    id: 'build-a428d0b4df49',
    document_id: 'spdoc-29b45c9a1102',
    document_title: 'A build of its own',
    state: 'running',
    driver: 'flow',
    level: 'fast',
    lead: null,
    loop_id: 'loop-a8846d2ab3f0',
    loop: { id: 'loop-a8846d2ab3f0', name: 'A build of its own', enabled: true },
    tasks_total: 2,
    tasks_done: 1,
    tasks_landing: 0,
    landings: [
      {
        task_id: 'task-e8907d605351',
        display_id: 'BO-2',
        title: 'Build beta',
        status: 'revision_needed',
        landing_state: 'sent_back',
        reason: REASON,
      },
    ],
    spent_usd: 0.0,
    stop_reason: null,
    created_at: '2026-11-13T17:35:14.089978+00:00',
    stopped_at: null,
    open_questions: 0,
    question: null,
    ...overrides,
  }
}

function flowLoop(overrides: Partial<LoopSummary> = {}): LoopSummary {
  return {
    id: 'loop-a8846d2ab3f0',
    label: 'A build of its own',
    purpose: '',
    stop_when_queue_empties: true,
    ending_state: null,
    queue: { approved: 1, revision_needed: 1 },
    open_questions: 0,
    firing_active: false,
    ...overrides,
  } as LoopSummary
}

function renderRunning(builds: ProjectBuildRow[], loops: LoopSummary[] = [flowLoop()]) {
  const items = runningItems({ builds, loops, jobs: [], now: NOW })
  render(<RunningTab items={items} colorIndexOf={() => 0} onOpen={() => {}} onAttend={() => {}} />)
  return items
}

describe('a build counts as done only landed tasks (FR-4)', () => {
  it('ac-progress: one landed, one approved and queued, one in progress reads 1 done, 1 landing, of 3', () => {
    const row = routeRow({
      tasks_total: 3,
      tasks_done: 1,
      tasks_landing: 1,
      landings: [{ task_id: 'task-b', display_id: 'BO-2', title: 'Build beta', status: 'approved', landing_state: 'queued', reason: '' }],
    })
    const [item] = renderRunning([row])
    expect(item.progress).toEqual({ done: 1, landing: 1, total: 3 })
    expect(screen.getByLabelText('1 of 3 tasks done, 1 landing')).toHaveTextContent('1/3 tasks · 1 landing')
  })
})

describe('Running lists a build until it finishes, with each landing (FR-6)', () => {
  it("ac-running: a task sent back by landing shows 'sent back' with the landing's reason, under Now", () => {
    renderRunning([routeRow()])
    const now = screen.getByRole('region', { name: 'Between steps' })
    expect(within(now).getByText('A build of its own')).toBeInTheDocument()
    const landing = screen.getByTestId('running-landing-task-e8907d605351')
    expect(landing).toHaveAttribute('data-failed', 'true')
    expect(within(landing).getByText('BO-2')).toBeInTheDocument()
    expect(within(landing).getByText('sent back')).toBeInTheDocument()
    expect(landing.textContent).toContain("makes the project's check `hub-tests` fail")
  })

  it("stays under Now while its flow has ended: a running build is not finished until it lands", () => {
    // A build reopened because an approved task had not landed keeps the loop that ended.
    const row = routeRow({
      tasks_landing: 1,
      landings: [{ task_id: 'task-b', display_id: 'BO-2', title: 'Build beta', status: 'approved', landing_state: 'held', reason: 'behind BO-1' }],
    })
    renderRunning([row], [flowLoop({ ending_state: 'completed' })])
    expect(screen.queryByRole('region', { name: 'Finished' })).toBeNull()
    expect(screen.getByText('Waiting for a task to land')).toBeInTheDocument()
    const landing = screen.getByTestId('running-landing-task-b')
    expect(within(landing).getByText('held')).toBeInTheDocument()
    expect(within(landing).getByText('behind BO-1')).toBeInTheDocument()
  })

  it('names every landing state in words, in the order the route lists the tasks', () => {
    const states = ['queued', 'checking', 'landing', 'held', 'pushed', 'not_landed', 'sent_back']
    const row = routeRow({
      tasks_total: states.length,
      tasks_done: 0,
      tasks_landing: 5,
      landings: states.map((state, i) => ({
        task_id: `task-${i}`,
        display_id: `BO-${i + 1}`,
        title: `Task ${i + 1}`,
        status: state === 'sent_back' ? 'revision_needed' : 'approved',
        landing_state: state,
        reason: '',
      })),
    })
    renderRunning([row])
    const words = screen.getAllByTestId(/^running-landing-/).map((li) => li.querySelector('.aw-run-landing-word')?.textContent)
    expect(words).toEqual([
      'waiting to land',
      'being checked',
      'landing',
      'held',
      'waiting for its pull request to merge',
      'did not land',
      'sent back',
    ])
  })

  it('a finished build lists no landings and reads finished', () => {
    renderRunning([routeRow({ state: 'finished', tasks_done: 2, landings: [], stopped_at: '2026-11-13T17:50:00Z' })], [flowLoop({ ending_state: 'completed' })])
    expect(screen.queryByTestId(/^running-landing-/)).toBeNull()
  })
})

describe('a board card tells landed from waiting to land (FR-7)', () => {
  const approved = {
    status: 'approved',
    priority: 'medium',
    assignee: 'QA',
    builder: 'DeveloperOpus',
    stage_since: '2026-11-13T17:00:00Z',
  }
  const landed = { ...approved, id: 'task-landed', readable_id: 'WD-1', title: 'Landed work', stage: 'on_main', stage_detail: 'cb86cc0' } as unknown as Task
  const waiting = { ...approved, id: 'task-waiting', readable_id: 'WD-2', title: 'Waiting work', stage: 'approved_waiting' } as unknown as Task

  it('ac-card: the two cards read differently and the unlanded one names its landing state', () => {
    render(
      <>
        <TaskCard task={landed} now={NOW} onOpen={() => {}} />
        <TaskCard task={waiting} now={NOW} onOpen={() => {}} />
      </>,
    )
    const landedStage = screen.getByTestId('task-stage-task-landed')
    const waitingStage = screen.getByTestId('task-stage-task-waiting')
    expect(landedStage.querySelector('.aw-tcard-word')).toHaveTextContent('On main')
    expect(waitingStage.querySelector('.aw-tcard-word')).toHaveTextContent('Waiting to land')
    expect(landedStage.closest('article')).toHaveAttribute('data-tone', 'done')
    expect(waitingStage.closest('article')).not.toHaveAttribute('data-tone', 'done')
  })
})
