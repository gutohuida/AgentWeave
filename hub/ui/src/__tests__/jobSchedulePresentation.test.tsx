import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { JobCard } from '@/components/jobs/JobCard'
import { JobForm } from '@/components/jobs/JobForm'
import type { Job, JobRun } from '@/api/jobs'

/**
 * The three things the approved S8-jobs mock specified and that had never shipped — the cron
 * translation, the next-run preview, the run-health strip — plus the two colour defects the audit
 * found in the same files.
 */

let jobHistory: { data?: JobRun[]; isLoading: boolean } = { data: [], isLoading: false }

vi.mock('@/api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/jobs')>()
  return { ...actual, useJobHistory: () => jobHistory }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useTasks: () => ({ data: [] }) }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: [] }) }
})

function baseJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    project_id: 'proj-1',
    name: 'Nightly audit',
    agent: 'claude',
    message: 'do the thing',
    cron: '0 9 * * 1-5',
    session_mode: 'new',
    enabled: true,
    source: 'hub',
    created_at: '2026-08-16T00:00:00Z',
    run_count: 0,
    ...overrides,
  }
}

function run(id: string, status: string): JobRun {
  return { id, job_id: 'job-1', fired_at: '2026-08-21T09:00:00Z', status, trigger: 'scheduled' }
}

const noop = () => {}

function renderCard(job: Job) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobCard job={job} onRun={noop} onPause={noop} onResume={noop} onArchive={noop} isPending={false} />
    </QueryClientProvider>,
  )
}

describe('JobCard schedule presentation', () => {
  it('says the cron expression in English beside the raw chip', () => {
    renderCard(baseJob())
    expect(screen.getByText('0 9 * * 1-5')).toBeInTheDocument()
    expect(screen.getByText('Weekdays at 9:00 AM')).toBeInTheDocument()
  })

  it('says nothing at all for a schedule it cannot translate exactly', () => {
    // Day-of-month and day-of-week both restricted: OR in Vixie cron, AND in APScheduler.
    const { container } = renderCard(baseJob({ cron: '0 9 15 * 1' }))
    expect(container.querySelector('.job-cron-plain')).toBeNull()
    expect(screen.getByText('0 9 15 * 1')).toBeInTheDocument()
  })
})

describe('JobCard run-health strip', () => {
  afterEach(() => {
    jobHistory = { data: [], isLoading: false }
  })

  it('draws one dot per recent firing, oldest first, coloured by outcome', () => {
    const job = baseJob({
      history: [run('r5', 'completed'), run('r4', 'skipped'), run('r3', 'completed'), run('r2', 'completed'), run('r1', 'failed')],
    })
    const { container } = renderCard(job)

    const dots = container.querySelectorAll('.trend-dot')
    expect(dots).toHaveLength(5)
    // Oldest on the left: the failed run is the last element of the newest-first payload.
    expect((dots[0] as HTMLElement).style.background).toContain('--red')
    expect((dots[4] as HTMLElement).style.background).toContain('--green')
    expect((dots[3] as HTMLElement).style.background).toContain('--amber')
    expect(screen.getByText('Last 5')).toBeInTheDocument()
  })

  it('states the outcomes in words, not colour alone', () => {
    jobHistory = { data: [], isLoading: false }
    renderCard(baseJob({ history: [run('r2', 'completed'), run('r1', 'failed')] }))
    expect(screen.getByLabelText('Recent runs: 1 failed, 1 completed')).toBeInTheDocument()
    expect(screen.getByText('Last 2')).toBeInTheDocument()
  })

  it('renders nothing when no history is in hand — GET /jobs does not carry it', () => {
    // `JobResponse.history` is "Included in get_job only", and the per-card fetch is gated on
    // `expanded`, so a collapsed card must not turn the strip into a request per row.
    jobHistory = { data: undefined, isLoading: false }
    const { container } = renderCard(baseJob())
    expect(container.querySelector('.trend-row')).toBeNull()
  })
})

describe('JobCard action and category colour', () => {
  it('carries the Local source as a neutral category, not as amber attention', () => {
    renderCard(baseJob({ source: 'local' }))
    const badge = screen.getByText('Local').closest('.aw-chip') as HTMLElement
    expect(badge.style.color).toContain('--text-2')
    expect(badge.getAttribute('style')).not.toContain('--amber')
  })

  it('gives Archive the destructive vocabulary instead of an outline that swallowed its red', () => {
    renderCard(baseJob())
    const archive = screen.getByLabelText('Archive')
    // The outline variant forces its own SVG to --text-2, so the inline red this used to carry
    // rendered nothing; `destructive` is the variant the confirm step already uses.
    expect(archive.className).toContain('--error-cont')
    expect(archive.getAttribute('style') ?? '').not.toContain('--red')
  })
})

describe('JobForm schedule preview', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('translates the cron field and previews when it will actually fire', () => {
    // Monday. The preview is computed from `new Date()` at render, so it has to be pinned.
    vi.useFakeTimers({ shouldAdvanceTime: true, now: new Date('2026-08-24T10:00:00Z') })
    render(<JobForm onSubmit={noop} onCancel={noop} isPending={false} />)

    // The form's own default is `0 9 * * *`.
    expect(screen.getByTestId('cron-preview')).toHaveTextContent('Daily at 9:00 AM')
    expect(screen.getByTestId('next-run-preview')).toHaveTextContent(
      'Next 3 runs: tomorrow 9:00 AM · Wed 9:00 AM · Thu 9:00 AM (server time)',
    )
  })
})
