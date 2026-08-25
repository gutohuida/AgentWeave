/**
 * The Hub's timestamps are UTC and, since `hub/hub/db/models.py`'s `UTCDateTime` column type,
 * always labelled as such by the time they reach the API — `hubDate` is a thin pass-through kept
 * as the single seam every Hub timestamp is required to go through (see the sweep test below),
 * not a compensation for a bug that used to live here.
 */
import { describe, expect, it } from 'vitest'
import { hubDate } from '@/lib/hubTime'

describe('hubDate', () => {
  it('parses an aware Hub timestamp', () => {
    // The same field comes back with fractional seconds from PATCH /jobs/{job_id} and
    // without from GET /loops/{loop_id}, so both shapes reach the same component.
    expect(hubDate('2026-08-19T19:09:01.285899Z').toISOString()).toBe('2026-08-19T19:09:01.285Z')
  })

  it('respects an explicit non-UTC offset', () => {
    expect(hubDate('2026-08-19T20:09:01+01:00').toISOString()).toBe('2026-08-19T19:09:01.000Z')
    expect(hubDate('2026-08-19T18:09:01-01:00').toISOString()).toBe('2026-08-19T19:09:01.000Z')
  })
})

/** The two call sites allowed to parse a date without `hubDate`, each because its input is not a
 *  Hub timestamp at all. Both say so at the line; this list is the second lock. */
const EXEMPT = new Set([
  // Wall-clock time the operator typed into a `datetime-local` input.
  'components/jobs/JobForm.tsx',
  // React Query's own epoch milliseconds, measured in this browser.
  'components/logs/LogsView.tsx',
  // Epoch milliseconds this module computed itself while walking a cron expression forward —
  // never a Hub timestamp string, so there is nothing for `hubDate` to normalise.
  'lib/cron.ts',
  // The helper itself.
  'lib/hubTime.ts',
])

/** Vite's own source graph rather than `node:fs` — the production build type-checks this file
 *  against the app's tsconfig, which has no node types, and reading the tree through the bundler
 *  is what a Vite project has for this anyway. */
const SOURCES: Record<string, string> = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

describe('every Hub timestamp is parsed through hubDate', () => {
  it('leaves no raw `new Date(value)` outside the two sites that are not Hub timestamps', () => {
    // A sweep is only worth doing once. Without this, the next component to render a timestamp
    // quietly reintroduces the hour-stale bug and nothing says so.
    const files = Object.keys(SOURCES)
      .map((path) => path.replace(/^\.\.\//, ''))
      .filter((path) => !path.startsWith('__tests__/'))

    // A scan that walked nothing would pass this test forever. It also has to be finding the
    // exempt files, or the exemption list is being matched against the wrong path shape.
    expect(files.length).toBeGreaterThan(50)
    for (const exempt of EXEMPT) expect(files).toContain(exempt)

    // `new Date()` with no argument means "now" and is always fine.
    const offenders = files.filter(
      (path) => !EXEMPT.has(path) && /new Date\([^)]/.test(SOURCES[`../${path}`]),
    )

    expect(offenders).toEqual([])
  })
})
