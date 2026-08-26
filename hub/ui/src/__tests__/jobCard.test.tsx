import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { JobCard } from '@/components/jobs/JobCard'
import type { Job } from '@/api/jobs'

/**
 * `JobCard`'s loop block (design D5, tasks.md 5.4): present only when `job.loop` is set, absent —
 * byte-identical to before this change — otherwise (human-only check 8.1's own concern, verified
 * here the one way a test can: the DOM has no trace of it).
 */

let loopTasks: unknown[] = []

/** What `useJobHistory` returns for the card under test — the runs, and whether they are in flight. */
let jobHistory: { data?: unknown[]; isLoading: boolean } = { data: [], isLoading: false }

vi.mock('@/api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/jobs')>()
  return {
    ...actual,
    useJobHistory: () => jobHistory,
  }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return {
    ...actual,
    useTasks: () => ({ data: loopTasks }),
  }
})

function baseJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    project_id: 'proj-1',
    name: 'Nightly audit',
    agent: 'claude',
    message: 'do the thing',
    cron: '0 9 * * *',
    session_mode: 'new',
    enabled: true,
    source: 'hub',
    created_at: '2026-08-16T00:00:00Z',
    run_count: 0,
    ...overrides,
  }
}

const noop = () => {}

function renderCard(job: Job, onOpenTasks?: (taskIds: string[]) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobCard
        job={job}
        onRun={noop}
        onPause={noop}
        onResume={noop}
        onArchive={noop}
        isPending={false}
        onOpenTasks={onOpenTasks}
      />
    </QueryClientProvider>,
  )
}

describe('JobCard loop block', () => {
  it('offers an honest archive action and confirms it', async () => {
    const user = userEvent.setup()
    const onArchive = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <JobCard
          job={baseJob()}
          onRun={noop}
          onPause={noop}
          onResume={noop}
          onArchive={onArchive}
          isPending={false}
        />
      </QueryClientProvider>,
    )

    await user.click(screen.getByLabelText('Archive'))
    await user.click(screen.getByRole('button', { name: 'Archive' }))
    expect(onArchive).toHaveBeenCalledWith('job-1')
    expect(screen.queryByLabelText('Delete')).not.toBeInTheDocument()
  })

  it('renders no loop block for a plain job, even expanded', async () => {
    const user = userEvent.setup()
    loopTasks = []
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.queryByTestId('job-loop-block')).not.toBeInTheDocument()
  })

  it('lists every current item with its agent when a flow staffs several', async () => {
    // `loop-becomes-a-flow` task 9.3, design D15. The card took `current_tasks[0]` while a firing
    // could only claim one thing; a flow claims several, and showing the first implies it is the
    // only one — the card under-reports exactly when the operator most needs to know what is going
    // on.
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }, { id: 'task-3' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Dependency bumps',
          purpose: 'Keep dependencies current',
          stop_when_queue_empties: true,
          queue: { in_progress: 3 },
          current_tasks: [
            { id: 'task-1', title: 'Bump lodash', status: 'in_progress', agent: 'builder' },
            { id: 'task-2', title: 'Fix row 42', status: 'in_progress', agent: 'critic' },
            { id: 'task-3', title: 'Review schema', status: 'completed', agent: 'auditor' },
          ],
          open_questions: 0,
          firing_active: true,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    const list = screen.getByTestId('job-loop-current-tasks')
    expect(within(list).getByText('Bump lodash (in_progress)')).toBeInTheDocument()
    expect(within(list).getByText('Fix row 42 (in_progress)')).toBeInTheDocument()
    expect(within(list).getByText('Review schema (completed)')).toBeInTheDocument()
    for (const agent of ['builder', 'critic', 'auditor']) {
      expect(within(list).getByText(agent)).toBeInTheDocument()
    }
  })

  it('omits the agent label entirely when nobody is attributed', async () => {
    // Absent rather than blank, matching what the API sends: a reader is never shown an empty
    // space where a name should be. A blocked task with no assignee is the case that reaches this.
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Dependency bumps',
          purpose: 'Keep dependencies current',
          stop_when_queue_empties: true,
          queue: { blocked: 1 },
          current_tasks: [{ id: 'task-1', title: 'Waiting on you', status: 'blocked' }],
          open_questions: 1,
          firing_active: false,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    const list = screen.getByTestId('job-loop-current-tasks')
    expect(within(list).getByText('Waiting on you (blocked)')).toBeInTheDocument()
    expect(list.textContent).toBe('Waiting on you (blocked)')
  })

  it('renders purpose, queue counts, current item and open questions when job.loop is set', async () => {
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Dependency bumps',
          purpose: 'Keep dependencies current',
          stop_when_queue_empties: true,
          queue: { pending: 1, in_progress: 1 },
          current_tasks: [{ id: 'task-1', title: 'Bump lodash', status: 'in_progress' }],
          open_questions: 2,
          firing_active: false,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.getByTestId('job-loop-block')).toBeInTheDocument()
    expect(screen.getByText('Keep dependencies current')).toBeInTheDocument()
    expect(screen.getByText('pending: 1')).toBeInTheDocument()
    expect(screen.getByText('in_progress: 1')).toBeInTheDocument()
    expect(screen.getByText('Bump lodash (in_progress)')).toBeInTheDocument()
    expect(screen.getByText('2 open questions')).toBeInTheDocument()
    expect(within(screen.getByTestId('job-loop-block')).getByText('Active')).toBeInTheDocument()
    // Icon.tsx's ICONS map must carry an entry for "all_inclusive" — an unmapped name
    // renders null, silently dropping the loop glyph next to the "Loop" label.
    expect(
      within(screen.getByTestId('job-loop-block')).getByText('Loop').previousElementSibling,
    ).toBeInstanceOf(SVGElement)
  })

  it('shows the stop reason and a Stopped badge once the loop has stopped', async () => {
    const user = userEvent.setup()
    loopTasks = []
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Nightly scan job',
          purpose: 'Nightly scan',
          stop_when_queue_empties: true,
          stop_reason: 'queue empty',
          stopped_at: '2026-08-17T01:00:00Z',
          queue: {},
          current_tasks: [],
          open_questions: 0,
          firing_active: false,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.getByText('Stopped')).toBeInTheDocument()
    expect(screen.getByText('Stopped: queue empty')).toBeInTheDocument()
    expect(screen.getByText('No current item')).toBeInTheDocument()
  })

  it('opens every loop task id on clicking the current item, and only when onOpenTasks is given', async () => {
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }]
    const onOpenTasks = vi.fn()
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Bump job',
          purpose: '',
          stop_when_queue_empties: false,
          queue: { in_progress: 1 },
          current_tasks: [{ id: 'task-1', title: 'Bump lodash', status: 'in_progress' }],
          open_questions: 0,
          firing_active: false,
        },
      }),
      onOpenTasks,
    )

    await user.click(screen.getByLabelText('Expand job details'))
    await user.click(screen.getByText('Bump lodash (in_progress)'))
    expect(onOpenTasks).toHaveBeenCalledWith(['task-1', 'task-2'])
  })
})

/**
 * Broken-loop check 9.6: nothing got quieter that should not have. The jobs collection carries no
 * `history`, so an expanded card read "No runs yet" for a job whose firings had failed — a loud
 * failure rendered as a job that had never fired.
 */
describe('JobCard run history', () => {
  it('shows a failed firing and its reason instead of "No runs yet"', async () => {
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-1',
          job_id: 'job-1',
          fired_at: '2026-08-21T09:00:00Z',
          status: 'failed',
          trigger: 'scheduled',
          error_summary: 'agent claude has no runner bound',
        },
      ],
      isLoading: false,
    }
    // No `history` on the job itself — exactly what `GET /jobs` returns.
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument()
    expect(screen.getByText('agent claude has no runner bound')).toBeInTheDocument()
  })

  it('does not claim "No runs yet" while the history is still loading', async () => {
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = { data: undefined, isLoading: true }
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.queryByText('No runs yet')).not.toBeInTheDocument()
    expect(screen.getByText('Loading runs…')).toBeInTheDocument()
  })

  it('still says "No runs yet" for a job that genuinely has not fired', async () => {
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = { data: [], isLoading: false }
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.getByText('No runs yet')).toBeInTheDocument()
  })

  /**
   * A continuing stall counts in place (design D6): no new row, and `fired_at` stays at the first
   * refusal so later real firings still sort above it. That is right for the history as a whole
   * and wrong for the row on its own — text frozen, timestamp ageing — which is a loop being
   * re-checked every five minutes wearing the appearance of one nobody has touched. The count is
   * the only thing separating the two, and it was recorded but not rendered.
   */
  it('says how many times a stalled firing has been re-checked', async () => {
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-stall',
          job_id: 'job-1',
          fired_at: '2026-08-24T09:00:00Z',
          status: 'skipped',
          trigger: 'scheduled',
          error_summary: 'loop queue is stalled: no claimable task among 2 open (2 completed)',
          tick_count: 9,
        },
      ],
      isLoading: false,
    }
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.getByTestId('job-run-ticks-run-stall')).toHaveTextContent('re-checked 9 times')
  })

  it('does not label a single firing as re-checked', async () => {
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-once',
          job_id: 'job-1',
          fired_at: '2026-08-24T09:00:00Z',
          status: 'skipped',
          trigger: 'scheduled',
          error_summary: 'loop queue is stalled: no claimable task among 1 open (1 completed)',
          tick_count: 1,
        },
      ],
      isLoading: false,
    }
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.queryByTestId('job-run-ticks-run-once')).not.toBeInTheDocument()
  })
})

describe('JobCard: what the row and the chips actually claim', () => {
  it('leads a refused firing with its own status, not with "scheduled" (F24)', async () => {
    // Measured 2026-08-25 on a real stall row: the first token read `scheduled`, in the neutral
    // text colour, an inch from its own amber stall reason. The `JobRun`'s status was `skipped`
    // all along, and both user test guides tell the operator to look for "one skipped row" — which
    // is exactly what the UI did not say. A row reading "scheduled" and "stalled" at once makes
    // the reader work out which word to believe.
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-stall',
          job_id: 'job-1',
          fired_at: '2026-08-25T09:00:00Z',
          status: 'skipped',
          trigger: 'scheduled',
          error_summary: 'loop queue is stalled: no claimable task among 1 open (1 completed)',
          tick_count: 5,
        },
      ],
      isLoading: false,
    }
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))

    expect(screen.getByTestId('job-run-status-run-stall')).toHaveTextContent('skipped')
    // The trigger stays — it answers a different question, whether the cron fired this or a
    // person did — it just is not the row's headline any more.
    expect(screen.getByText('scheduled')).toBeInTheDocument()
  })

  it('names the refusals beside a "0 runs" chip so the two counts agree (F25)', async () => {
    // Neither number was wrong. `run_count` counts firings that actually ran, so a queue that has
    // only ever refused is honestly zero — but the card then showed `0 runs` above a Recent Runs
    // list holding one entry, and a reader meets those as two counts of the same word.
    const user = userEvent.setup()
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-stall',
          job_id: 'job-1',
          fired_at: '2026-08-25T09:00:00Z',
          status: 'skipped',
          trigger: 'scheduled',
          error_summary: 'loop queue is stalled',
        },
      ],
      isLoading: false,
    }
    renderCard(baseJob({ run_count: 0 }))

    expect(screen.getByText('0 runs')).toBeInTheDocument()
    expect(screen.getByTestId('job-refused-job-1')).toHaveTextContent('1 refused')

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.getByTestId('job-run-status-run-stall')).toHaveTextContent('skipped')
  })

  it('does not claim refusals when every firing ran (F25)', async () => {
    loopTasks = []
    jobHistory = {
      data: [
        {
          id: 'run-ok',
          job_id: 'job-1',
          fired_at: '2026-08-25T09:00:00Z',
          status: 'completed',
          trigger: 'scheduled',
        },
      ],
      isLoading: false,
    }
    renderCard(baseJob({ run_count: 1 }))

    expect(screen.getByText('1 runs')).toBeInTheDocument()
    expect(screen.queryByTestId('job-refused-job-1')).not.toBeInTheDocument()
  })

  it('says a prospective reviewer is next, not that it is working the task (F26)', async () => {
    // `completed | relay` read as "relay is working this" and meant "relay is who would review
    // this". The value was right and the presentation wrong, and the column's meaning changed
    // silently with the task's status — unreadable once a flow puts three such lines on one card.
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }, { id: 'task-3' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Ledger fixes',
          purpose: 'Land the balance fix',
          stop_when_queue_empties: true,
          queue: { in_progress: 1, completed: 1, blocked: 1 },
          current_tasks: [
            {
              id: 'task-1',
              title: 'Fix row 42',
              status: 'in_progress',
              agent: 'builder',
              agent_capacity: 'working',
            },
            {
              id: 'task-2',
              title: 'Name the two totals',
              status: 'completed',
              agent: 'relay',
              agent_capacity: 'next',
            },
            {
              id: 'task-3',
              title: 'Await a decision',
              status: 'blocked',
              agent: 'critic',
              agent_capacity: 'assigned',
            },
          ],
          open_questions: 0,
          firing_active: true,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    const list = screen.getByTestId('job-loop-current-tasks')

    // Mid-turn: the bare name, exactly as before.
    expect(within(list).getByText('builder')).toBeInTheDocument()
    // A proposal, and it says so.
    expect(within(list).getByText('next: relay')).toBeInTheDocument()
    expect(within(list).queryByText('relay')).not.toBeInTheDocument()
    // Waiting on a person: the row's own assignee, and nobody is being selected for it.
    expect(within(list).getByText('assigned: critic')).toBeInTheDocument()
  })

  it('names a held review as waiting rather than as working (F63)', async () => {
    // Found live by the operator judging group 11's 11.5: a review turn had FAILED, no run existed
    // anywhere, and the card still read the bare name -- which means "this agent is mid-turn".
    // `held` is the state where the loop cannot staff anybody and nobody is running either, and it
    // has to look different from `working` or the split in the API buys nothing on screen.
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Ship it',
          purpose: 'Ship it',
          stop_when_queue_empties: false,
          queue: { completed: 2 },
          current_tasks: [
            {
              id: 'task-1',
              title: 'Reviewed by nobody right now',
              status: 'under_review',
              agent: 'critic',
              agent_capacity: 'held',
            },
            {
              id: 'task-2',
              title: 'Genuinely being worked',
              status: 'in_progress',
              agent: 'builder',
              agent_capacity: 'working',
            },
          ],
          open_questions: 0,
          firing_active: false,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    const list = screen.getByTestId('job-loop-current-tasks')

    expect(within(list).getByText('waiting on critic')).toBeInTheDocument()
    // The bare name is reserved for genuinely running work, which is the whole distinction.
    expect(within(list).queryByText('critic')).not.toBeInTheDocument()
    expect(within(list).getByText('builder')).toBeInTheDocument()
  })

  it('falls back to the bare name when the Hub sends no role (F26)', async () => {
    // A Hub older than this change sends `agent` without `agent_capacity`. It must render as it always
    // did rather than acquiring a qualifier the server never claimed.
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          label: 'Ledger fixes',
          purpose: 'Land the balance fix',
          stop_when_queue_empties: true,
          queue: { in_progress: 1 },
          current_tasks: [
            { id: 'task-1', title: 'Fix row 42', status: 'in_progress', agent: 'builder' },
          ],
          open_questions: 0,
          firing_active: true,
        },
      }),
    )

    await user.click(screen.getByLabelText('Expand job details'))
    expect(within(screen.getByTestId('job-loop-current-tasks')).getByText('builder')).toBeInTheDocument()
  })
})
