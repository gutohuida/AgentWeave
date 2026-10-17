import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ApiError } from '@/api/client'
import { ProjectLedger } from '@/components/activity/ProjectLedger'

/** A Hub that predates the ledger (the operator's running Hub, until it restarts onto this
 *  checkout) answers 404: the Activity tab still opens on the live log, and says why. */

vi.mock('@/api/ledger', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/ledger')>()),
  useProjectLedger: () => ({ data: undefined, isLoading: false, isError: true, error: new ApiError(404, 'Not Found') }),
}))
vi.mock('@/components/activity/ActivityLog', () => ({ ActivityLog: () => <div data-testid="live-log" /> }))

describe('ProjectLedger on a Hub without the ledger', () => {
  it('falls back to the live log with a note, not an error', () => {
    render(<ProjectLedger onOpenTask={vi.fn()} />)
    expect(screen.getByTestId('ledger-unavailable')).toHaveTextContent('predates the ledger')
    expect(screen.getByTestId('live-log')).toBeInTheDocument()
    expect(screen.queryByTestId('ledger-error')).toBeNull()
  })
})
