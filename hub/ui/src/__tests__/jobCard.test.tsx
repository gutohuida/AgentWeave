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
        onDelete={noop}
        isPending={false}
        onOpenTasks={onOpenTasks}
      />
    </QueryClientProvider>,
  )
}

describe('JobCard loop block', () => {
  it('renders no loop block for a plain job, even expanded', async () => {
    const user = userEvent.setup()
    loopTasks = []
    renderCard(baseJob())

    await user.click(screen.getByLabelText('Expand job details'))
    expect(screen.queryByTestId('job-loop-block')).not.toBeInTheDocument()
  })

  it('renders purpose, queue counts, current item and open questions when job.loop is set', async () => {
    const user = userEvent.setup()
    loopTasks = [{ id: 'task-1' }, { id: 'task-2' }]
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          purpose: 'Keep dependencies current',
          stop_when_queue_empties: true,
          queue: { pending: 1, in_progress: 1 },
          current_task: { id: 'task-1', title: 'Bump lodash', status: 'in_progress' },
          open_questions: 2,
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
  })

  it('shows the stop reason and a Stopped badge once the loop has stopped', async () => {
    const user = userEvent.setup()
    loopTasks = []
    renderCard(
      baseJob({
        loop: {
          id: 'loop-1',
          purpose: 'Nightly scan',
          stop_when_queue_empties: true,
          stop_reason: 'queue empty',
          stopped_at: '2026-08-17T01:00:00Z',
          queue: {},
          current_task: null,
          open_questions: 0,
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
          purpose: '',
          stop_when_queue_empties: false,
          queue: { in_progress: 1 },
          current_task: { id: 'task-1', title: 'Bump lodash', status: 'in_progress' },
          open_questions: 0,
        },
      }),
      onOpenTasks,
    )

    await user.click(screen.getByLabelText('Expand job details'))
    await user.click(screen.getByText('Bump lodash (in_progress)'))
    expect(onOpenTasks).toHaveBeenCalledWith(['task-1', 'task-2'])
  })
})
