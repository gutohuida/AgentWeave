import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { EventLogEntry } from '@/api/logs'

// The strip must derive its buckets from the entries already on screen — no second API call — so
// the whole test drives the component through the one hook it already had.
const logsResult: { current: { data: EventLogEntry[]; isLoading: boolean; dataUpdatedAt: number } } = {
  current: { data: [], isLoading: false, dataUpdatedAt: 0 },
}

vi.mock('@/api/logs', () => ({
  useLogs: () => logsResult.current,
  useLogAgents: () => ({ data: [] }),
}))

import { LogsView } from '@/components/logs/LogsView'

function withQueryClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>
}

function entry(id: string, minutesAgo: number, severity = 'info'): EventLogEntry {
  return {
    id,
    project_id: 'proj-test',
    event_type: `event_${id}`,
    severity,
    timestamp: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
    data: {},
  }
}

function setEntries(entries: EventLogEntry[], dataUpdatedAt = Date.now()) {
  logsResult.current = { data: entries, isLoading: false, dataUpdatedAt }
}

describe('LogsView volume strip', () => {
  beforeEach(() => {
    setEntries([])
  })

  it('buckets the entries already on screen into a fixed-width strip', () => {
    setEntries([entry('a', 0), entry('b', 4), entry('c', 12)])
    const { container } = render(withQueryClient(<LogsView />))

    expect(container.querySelectorAll('.log-volume-bar')).toHaveLength(20)
    expect(screen.getByRole('img', { name: /Log volume, last 30m/ })).toBeInTheDocument()
    expect(screen.getByText('last 30m')).toBeInTheDocument()
  })

  it('tints a bucket by the worst severity in it, and calls out the peak', () => {
    // Three entries land in one bucket 5 minutes back — the spike the strip exists to make
    // visible — with a quieter info entry elsewhere so the peak is a real maximum.
    setEntries([
      entry('e1', 5, 'error'),
      entry('e2', 5, 'error'),
      entry('e3', 5, 'error'),
      entry('i1', 20),
    ])
    const { container } = render(withQueryClient(<LogsView />))

    const bars = Array.from(container.querySelectorAll<HTMLElement>('.log-volume-bar'))
    const tinted = bars.filter((bar) => bar.style.background.includes('var(--red)'))
    expect(tinted).toHaveLength(1)

    // Buckets are 90s wide, so the callout normalises to entries/minute: 3 in 90s reads as 2/min.
    expect(screen.getByText('2/min')).toBeInTheDocument()
  })

  it('says which window it is showing when the feed has gone quiet', () => {
    // Nothing recent: anchoring on the newest entry keeps the last half hour of real activity
    // readable, and the note stops claiming the window ends now.
    setEntries([entry('old1', 120), entry('old2', 124)])
    render(withQueryClient(<LogsView />))

    expect(screen.queryByText('last 30m')).not.toBeInTheDocument()
    expect(screen.getByText(/^30m to \d{2}:\d{2}$/)).toBeInTheDocument()
  })

  it('spends no row on the strip when there is nothing to plot', () => {
    const { container } = render(withQueryClient(<LogsView />))
    expect(container.querySelector('.log-volume')).toBeNull()
  })
})

describe('LogsView arrival flash', () => {
  beforeEach(() => {
    setEntries([])
  })

  it('does not flash the payload that was already there when the view opened', async () => {
    setEntries([entry('a', 0), entry('b', 1)])
    const { container } = render(withQueryClient(<LogsView />))

    await waitFor(() => expect(container.querySelectorAll('.log-row-main')).toHaveLength(2))
    expect(container.querySelectorAll('.log-row-main.is-new')).toHaveLength(0)
  })

  it('flashes only the ids that were not in the previous payload', async () => {
    const first = [entry('a', 0)]
    setEntries(first)
    const { container, rerender } = render(withQueryClient(<LogsView />))
    await waitFor(() => expect(container.querySelectorAll('.log-row-main')).toHaveLength(1))

    setEntries([...first, entry('b', 0)])
    rerender(withQueryClient(<LogsView />))

    await waitFor(() => expect(container.querySelectorAll('.log-row-main.is-new')).toHaveLength(1))
    // The event type appears twice in a row (its own column and, unsummarised, the message
    // column) — either occurrence resolves to the same row.
    expect(screen.getAllByText('event_b')[0].closest('.log-row-main')).toHaveClass('is-new')
  })
})
