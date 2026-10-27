import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import * as React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '@/api/jobs'
import { JobsScreen } from '@/components/jobs/JobsScreen'
import { Dialog, DialogContent } from '@/components/ui/dialog'

/** The shared DialogContent (F1029): it gives focus back to whatever opened it, and keeps its
 *  Overlay and Content as direct children of Radix's Portal so Radix can hand each a ref (its exit
 *  animation waits on that ref; a wrapper function component cannot take one). */

const archive = vi.fn()
const idle = { mutate: vi.fn(), isPending: false }
const JOB: Job = {
  id: 'job-1', project_id: 'proj-1', name: 'Nightly', agent: 'claude', message: 'go', cron: '0 9 * * *',
  session_mode: 'new', enabled: true, source: 'hub', created_at: '2026-10-15T00:00:00Z', run_count: 1,
}

vi.mock('@/api/jobs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/jobs')>()),
  useJobs: () => ({ data: [JOB], isLoading: false }),
  useArchivedJobs: () => ({ data: [], isLoading: false }),
  useRunJob: () => idle,
  usePauseJob: () => idle,
  useResumeJob: () => idle,
  useArchiveJob: () => ({ mutate: archive, isPending: false }),
  useCreateJob: () => idle,
  useJobHistory: () => ({ data: [], isLoading: false }),
}))

afterEach(() => vi.restoreAllMocks())

function Harness() {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <button onClick={() => setOpen(true)}>Open it</button>
      <Dialog open={open} onOpenChange={setOpen}>
        {open ? <DialogContent title="A dialog" footer={<button onClick={() => setOpen(false)}>Done</button>} /> : null}
      </Dialog>
    </>
  )
}

describe('DialogContent', () => {
  it('hands Radix refs it can take: no function-component ref warning', async () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Open it' }))
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const refWarnings = errors.mock.calls.filter((call) => String(call[0]).includes('Function components cannot be given refs'))
    expect(refWarnings).toEqual([])
  })

  it('returns focus to the button that opened it', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open it' })
    opener.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(opener).toHaveFocus()
  })

  // The Jobs archive confirm is opened from a menu item that is unmounted as the menu closes.
  it('returns focus to the menu’s trigger after the Jobs archive confirm closes (F1029)', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <JobsScreen />
      </QueryClientProvider>,
    )
    const more = await screen.findByRole('button', { name: 'More for Nightly' })
    more.focus()
    await user.keyboard('{Enter}')
    await user.click(await screen.findByRole('menuitem', { name: 'Archive' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Archive Nightly?')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(more).toHaveFocus()
  })
})
