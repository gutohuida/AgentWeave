import { afterEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { refreshWorkSoon, WORK_REFRESH_MS } from '@/hooks/useSSE'

/** Every run and task event moves the ledger and the work tally, each a read over the whole
 *  history: a burst of events costs one refetch of each, a few seconds later. */
describe('refreshWorkSoon', () => {
  afterEach(() => vi.useRealTimers())

  it('refetches the ledger and the tally once for a burst of events', () => {
    vi.useFakeTimers()
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries').mockResolvedValue(undefined)
    for (let i = 0; i < 20; i++) refreshWorkSoon(client, 'proj-1')
    expect(spy).not.toHaveBeenCalled()
    vi.advanceTimersByTime(WORK_REFRESH_MS)
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[2])).toEqual(['ledger', 'stats'])
    refreshWorkSoon(client, 'proj-1')
    vi.advanceTimersByTime(WORK_REFRESH_MS)
    expect(spy).toHaveBeenCalledTimes(4)
  })
})
