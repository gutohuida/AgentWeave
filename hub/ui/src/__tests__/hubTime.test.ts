/**
 * The Hub's timestamps are UTC; only their label is sometimes missing.
 *
 * SQLite stores no timezone, so a datetime read back through SQLAlchemy is naive and Pydantic
 * serialises it bare. `new Date()` reads a bare date-time string as local, so on a machine that is
 * not on UTC every relative time is wrong by that offset — measured on the trial Hub 2026-08-19
 * (UTC+1): an edit staged seconds earlier rendered as "about 1 hour ago".
 */
import { describe, expect, it } from 'vitest'
import { hubDate } from '@/lib/hubTime'

describe('hubDate', () => {
  it('reads a bare Hub timestamp as UTC, not as local time', () => {
    expect(hubDate('2026-08-19T19:09:01.285899').toISOString()).toBe('2026-08-19T19:09:01.285Z')
  })

  it('leaves a timestamp that already says UTC alone', () => {
    // The same field comes back aware from PATCH /jobs/{job_id} and naive from GET
    // /loops/{loop_id}, so both shapes reach the same component.
    expect(hubDate('2026-08-19T19:09:01.285899Z').toISOString()).toBe('2026-08-19T19:09:01.285Z')
  })

  it('respects an explicit offset rather than overriding it', () => {
    expect(hubDate('2026-08-19T20:09:01+01:00').toISOString()).toBe('2026-08-19T19:09:01.000Z')
    expect(hubDate('2026-08-19T18:09:01-01:00').toISOString()).toBe('2026-08-19T19:09:01.000Z')
  })

  it('does not mistake the date’s own hyphens for an offset', () => {
    expect(hubDate('2026-08-19T19:09:01').toISOString()).toBe('2026-08-19T19:09:01.000Z')
  })
})
