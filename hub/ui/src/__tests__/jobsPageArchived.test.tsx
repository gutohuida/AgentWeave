import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { Job } from '@/api/jobs'
import { JobsPage } from '@/components/jobs/JobsPage'

/** F637: after every job was archived, the Jobs page said "No jobs yet / Create First Job" although
 *  six had fired. Archived jobs are listed on their own, and the empty state counts them. */

let live: Job[] = []
let archived: Job[] = []
const idle = { mutate: vi.fn(), isPending: false }

vi.mock('@/api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/jobs')>()
  return {
    ...actual,
    useJobs: () => ({ data: live, isLoading: false }),
    useArchivedJobs: () => ({ data: archived, isLoading: false }),
    useRunJob: () => idle,
    usePauseJob: () => idle,
    useResumeJob: () => idle,
    useArchiveJob: () => idle,
    useCreateJob: () => idle,
    useJobHistory: () => ({ data: [], isLoading: false }),
  }
})

function job(id: string, overrides: Partial<Job> = {}): Job {
  return {
    id,
    project_id: 'proj-1',
    name: `Job ${id}`,
    agent: 'claude',
    message: 'go',
    cron: '0 9 * * *',
    session_mode: 'new',
    enabled: false,
    source: 'hub',
    created_at: '2026-10-15T00:00:00Z',
    run_count: 2,
    ...overrides,
  }
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobsPage />
    </QueryClientProvider>,
  )
}

describe('the Jobs page and archived jobs (F637)', () => {
  beforeEach(() => {
    live = []
    archived = []
  })

  it('does not call a project with archived jobs empty, and lists them on request', () => {
    archived = [
      job('a', { archived_at: '2026-10-15T10:00:00Z' }),
      job('b', { archived_at: '2026-10-15T11:00:00Z' }),
    ]
    renderPage()
    expect(screen.queryByText('No jobs yet')).toBeNull()
    expect(screen.getByText('No active or paused jobs')).toBeInTheDocument()
    expect(screen.getByText(/2 archived/)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('jobs-filter-archived'))
    expect(screen.getByTestId('archived-job-a')).toHaveTextContent('Job a')
    expect(screen.getByTestId('archived-job-b')).toHaveTextContent('archived')
  })

  it('still says No jobs yet when nothing was ever made', () => {
    renderPage()
    expect(screen.getByText('No jobs yet')).toBeInTheDocument()
  })
})
