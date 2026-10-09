import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

// F552. The category chips offered `transport` and `watchdog`; both subsystems were deleted and
// nothing the Hub writes carries either category, so the chips filtered to nothing, always.
vi.mock('@/api/logs', () => ({
  useLogs: () => ({ data: [], isLoading: false, dataUpdatedAt: 0 }),
  useLogAgents: () => ({ data: [] }),
}))
vi.mock('@/api/agents', () => ({ useAgents: () => ({ data: [], error: null }) }))

import { LogsView } from '@/components/logs/LogsView'

describe('the Logs category chips (F552)', () => {
  it('offer no category for a subsystem that no longer exists', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <LogsView />
      </QueryClientProvider>,
    )

    expect(screen.getByRole('button', { name: 'runner' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'watchdog' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'transport' })).toBeNull()
  })
})
