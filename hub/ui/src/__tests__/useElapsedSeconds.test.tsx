import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatElapsedSeconds, useElapsedSeconds } from '@/hooks/useElapsedSeconds'

const NOW = Date.parse('2026-08-20T12:00:00.000Z')

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useElapsedSeconds', () => {
  it('reports a run age from the Hub timestamp, not from when it started watching', () => {
    // The reported defect: leaving a conversation unmounts the pane, so returning to a run
    // that had been going for minutes showed a counter that had just restarted at zero.
    // Mounting fresh against a run that began 90 seconds ago must read 90, not 0.
    const startedNinetySecondsAgo = new Date(NOW - 90_000).toISOString()

    const { result } = renderHook(() => useElapsedSeconds(true, startedNinetySecondsAgo))

    expect(result.current).toBe(90)
  })

  it('keeps counting from that origin', () => {
    const startedAt = new Date(NOW - 90_000).toISOString()
    const { result } = renderHook(() => useElapsedSeconds(true, startedAt))

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(result.current).toBe(92)
  })

  it('survives a remount, because the origin is a property of the run', () => {
    const startedAt = new Date(NOW - 45_000).toISOString()
    const first = renderHook(() => useElapsedSeconds(true, startedAt))
    expect(first.result.current).toBe(45)
    first.unmount()

    const second = renderHook(() => useElapsedSeconds(true, startedAt))
    expect(second.result.current).toBe(45)
  })

  it('re-bases when the timestamp arrives after the run was observed', () => {
    // A run can be seen as active before its first entry is persisted, so `since` starts
    // null and lands a moment later. The count must move to the real origin, not stay at 0.
    const { result, rerender } = renderHook(
      ({ since }: { since: string | null }) => useElapsedSeconds(true, since),
      { initialProps: { since: null as string | null } }
    )
    expect(result.current).toBe(0)

    rerender({ since: new Date(NOW - 30_000).toISOString() })

    expect(result.current).toBe(30)
  })

  it('falls back to the transition when there is no timestamp to derive from', () => {
    const { result } = renderHook(() => useElapsedSeconds(true, null))
    expect(result.current).toBe(0)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current).toBe(3)
  })

  it('never reports a negative age when the Hub clock is ahead of the browser', () => {
    const startedInTheFuture = new Date(NOW + 5_000).toISOString()
    const { result } = renderHook(() => useElapsedSeconds(true, startedInTheFuture))
    expect(result.current).toBe(0)
  })

  it('ignores an unparseable timestamp rather than rendering NaN', () => {
    const { result } = renderHook(() => useElapsedSeconds(true, 'not a date'))
    expect(result.current).toBe(0)
  })

  it('reads null while inactive', () => {
    const { result } = renderHook(() =>
      useElapsedSeconds(false, new Date(NOW - 10_000).toISOString())
    )
    expect(result.current).toBeNull()
  })
})

describe('formatElapsedSeconds', () => {
  it('reads seconds under a minute and m:ss at or beyond one', () => {
    expect(formatElapsedSeconds(12)).toBe('12s')
    expect(formatElapsedSeconds(59)).toBe('59s')
    expect(formatElapsedSeconds(60)).toBe('1:00')
    expect(formatElapsedSeconds(63)).toBe('1:03')
    expect(formatElapsedSeconds(600)).toBe('10:00')
  })
})
