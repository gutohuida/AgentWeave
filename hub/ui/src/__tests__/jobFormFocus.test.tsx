import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { vi } from 'vitest'
import { JobsPage } from '@/components/jobs/JobsPage'
import { JobForm } from '@/components/jobs/JobForm'

// Task 1.11: `JobForm`'s header carries a Close button that is first in DOM order, ahead of the
// Job Name input — so unlike the confirm-only dialogs (task 1.5/2.3), D1's `marked ?? first ??
// panel` fallback does NOT already land focus on the Name input here. This is the one of the
// three remaining group-2 forms where the mark changes observed behaviour rather than merely
// defending against reordering.
vi.mock('@/api/jobs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/jobs')>()
  const idle = () => ({ mutate: vi.fn(), isPending: false })
  return {
    ...actual,
    useJobs: () => ({ data: [], isLoading: false }),
    useRunJob: idle,
    usePauseJob: idle,
    useResumeJob: idle,
    useArchiveJob: idle,
    useCreateJob: idle,
  }
})

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: [] }) }
})

function renderJobsPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <JobsPage />
    </QueryClientProvider>,
  )
}

describe('JobForm focus (task 1.11)', () => {
  it('puts focus on the Job Name input, not the header Close button, when the form opens', async () => {
    const user = userEvent.setup()
    renderJobsPage()

    const trigger = screen.getByRole('button', { name: /New Job/i })
    trigger.focus()
    await user.click(trigger)

    expect(screen.getByPlaceholderText(/Daily Standup/i)).toHaveFocus()
  })

  it('calls onCancel on Escape and returns focus to the opener', async () => {
    const user = userEvent.setup()
    renderJobsPage()

    const trigger = screen.getByRole('button', { name: /New Job/i })
    trigger.focus()
    await user.click(trigger)

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
})

describe('1.13 JobForm — focus moves to the panel when isPending becomes true', () => {
  it('Create holds focus, then isPending turns true: focus moves off the now-disabled button, to the panel', () => {
    const { container, rerender } = render(
      <JobForm onSubmit={() => {}} onCancel={() => {}} isPending={false} />,
    )

    const createButton = screen.getByRole('button', { name: /Create Job/i })
    createButton.focus()
    expect(document.activeElement).toBe(createButton)

    rerender(<JobForm onSubmit={() => {}} onCancel={() => {}} isPending={true} />)

    const panel = container.querySelector('[tabindex="-1"]')
    expect(document.activeElement).not.toBe(createButton)
    expect(document.activeElement).toBe(panel)
  })
})
