import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { JobsPage } from '@/components/jobs/JobsPage'
import { ApiError } from '@/api/client'
import type { Job } from '@/api/jobs'

/**
 * F411: pressing Run on a job the Hub declines used to show the operator nothing -- `useRunJob`
 * had no `onError` and `JobsPage` passed `runJob.mutate` bare, so the 409/500 that names the reason
 * was dropped. The page now shows it, the way it already showed an Archive refusal.
 */

let runRefusal: unknown = null

vi.mock('@/api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/jobs')>()
  const idle = () => ({ mutate: vi.fn(), isPending: false })
  return {
    ...actual,
    useJobs: () => ({ data: [pageJob()], isLoading: false }),
    // A Run that the Hub declines: the mutation reports through the per-call `onError`, as
    // react-query does for a rejected request.
    useRunJob: () => ({
      mutate: (_id: string, opts?: { onError?: (e: unknown) => void }) => opts?.onError?.(runRefusal),
      isPending: false,
    }),
    usePauseJob: idle,
    useResumeJob: idle,
    useArchiveJob: idle,
    useCreateJob: idle,
  }
})

vi.mock('@/api/tasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/tasks')>()
  return { ...actual, useTasks: () => ({ data: [] }) }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: [] }) }
})

function pageJob(): Job {
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
    created_at: '2026-01-01T00:00:00Z',
    run_count: 0,
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

describe('F411 -- a declined Run is shown to the operator', () => {
  it('shows the Hub detail when Run is refused', async () => {
    runRefusal = new ApiError(
      409,
      JSON.stringify({ detail: 'Agent claude is busy with another turn; try again when it finishes.' }),
    )
    renderPage()
    await userEvent.setup().click(screen.getByRole('button', { name: /^Run$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/busy with another turn/)
  })

  it('says it was Run that failed when the body carries no detail', async () => {
    runRefusal = new ApiError(500, 'Internal Server Error')
    renderPage()
    await userEvent.setup().click(screen.getByRole('button', { name: /^Run$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Internal Server Error/)
  })

  it('clears the earlier refusal when the next press starts', async () => {
    runRefusal = new ApiError(409, JSON.stringify({ detail: 'first reason' }))
    renderPage()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /^Run$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('first reason')
    runRefusal = new ApiError(409, JSON.stringify({ detail: 'second reason' }))
    await user.click(screen.getByRole('button', { name: /^Run$/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('second reason')
    expect(screen.queryByText('first reason')).not.toBeInTheDocument()
  })
})
