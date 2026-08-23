import { describe, it, expect } from 'vitest'
import { describeCron, formatNextRun, nextRuns } from '@/lib/cron'

/**
 * `describeCron` exists to stop the operator parsing `0 9 * * 1-5` by eye, so the thing it must
 * never do is be confidently wrong. Half of this file is therefore the `null` cases: every shape
 * the module declines is asserted to decline, because a regression there is silent — a wrong
 * sentence reads exactly as convincingly as a right one.
 */
describe('describeCron — the shapes this product actually schedules', () => {
  it('translates the five presets JobForm offers', () => {
    // These are `CRON_EXAMPLES` in JobForm.tsx; the chip label and the translation must agree.
    expect(describeCron('0 9 * * *')).toBe('Daily at 9:00 AM')
    expect(describeCron('0 9 * * 1-5')).toBe('Weekdays at 9:00 AM')
    expect(describeCron('0 */6 * * *')).toBe('Every 6 hours')
    expect(describeCron('0 0 * * 0')).toBe('Sundays at 12:00 AM')
    expect(describeCron('0 0 1 * *')).toBe('The 1st of every month at 12:00 AM')
  })

  it('says the minute frequencies', () => {
    expect(describeCron('* * * * *')).toBe('Every minute')
    expect(describeCron('*/5 * * * *')).toBe('Every 5 minutes')
    expect(describeCron('*/15 * * * *')).toBe('Every 15 minutes')
    expect(describeCron('0 * * * *')).toBe('Every hour')
    expect(describeCron('30 * * * *')).toBe('Every hour at :30')
    // An evenly-spaced list that covers the hour is a rate, whichever way it was written.
    expect(describeCron('0,30 * * * *')).toBe('Every 30 minutes')
    expect(describeCron('0,20,45 * * * *')).toBe('Every hour at :00, :20 and :45')
  })

  it('names a window when a stride does not span the whole day', () => {
    expect(describeCron('0 9-17 * * 1-5')).toBe('Hourly from 9:00 AM to 5:00 PM on weekdays')
    expect(describeCron('0 6-20/2 * * *')).toBe('Every 2 hours from 6:00 AM to 8:00 PM')
    expect(describeCron('*/5 9-17 * * 1-5')).toBe(
      'Every 5 minutes from 9:00 AM to 5:59 PM on weekdays',
    )
    expect(describeCron('* 9 * * *')).toBe('Every minute from 9:00 AM to 9:59 AM')
  })

  it('enumerates a handful of clock times but not a hundred', () => {
    expect(describeCron('0 9,17 * * *')).toBe('Daily at 9:00 AM and 5:00 PM')
    expect(describeCron('0,30 9 * * *')).toBe('Daily at 9:00 AM and 9:30 AM')
    expect(describeCron('0 8-20/4 * * *')).toBe('Daily at 8:00 AM, 12:00 PM, 4:00 PM and 8:00 PM')
    expect(describeCron('30 7,12,18 * * 1-5')).toBe(
      'Weekdays at 7:30 AM, 12:30 PM and 6:30 PM',
    )
    // A list that happens to step across the whole day is still a rate, not four instants.
    expect(describeCron('15 0,6,12,18 * * *')).toBe('Every 6 hours at :15')
    // Past four instants, naming them stops being a translation — a rate takes over.
    expect(describeCron('*/5 9 * * *')).toBe('Every 5 minutes from 9:00 AM to 9:59 AM')
  })

  it('reads weekday sets, month days and month names', () => {
    expect(describeCron('0 9 * * 0,6')).toBe('Weekends at 9:00 AM')
    expect(describeCron('0 9 * * 6,0')).toBe('Weekends at 9:00 AM')
    expect(describeCron('0 9 * * 1,4')).toBe('Mondays and Thursdays at 9:00 AM')
    expect(describeCron('0 9 1,15 * *')).toBe('The 1st and 15th of every month at 9:00 AM')
    expect(describeCron('0 9 * 1 *')).toBe('Every day in January at 9:00 AM')
    expect(describeCron('0 9 * 1 1')).toBe('Mondays in January at 9:00 AM')
    expect(describeCron('0 0 1 1 *')).toBe('The 1st of January at 12:00 AM')
    expect(describeCron('*/10 * * 1 *')).toBe('Every 10 minutes in January')
  })

  it('accepts the three-letter aliases crontab accepts', () => {
    expect(describeCron('0 9 * * MON-FRI')).toBe('Weekdays at 9:00 AM')
    expect(describeCron('0 9 * JAN *')).toBe('Every day in January at 9:00 AM')
    // 7 and 0 are both Sunday, so `0,7` is one day, not two.
    expect(describeCron('0 9 * * 0,7')).toBe('Sundays at 9:00 AM')
  })

  it('gets ordinals and the 12-hour boundaries right', () => {
    expect(describeCron('0 12 * * *')).toBe('Daily at 12:00 PM')
    expect(describeCron('0 0 * * *')).toBe('Daily at 12:00 AM')
    expect(describeCron('0 9 2 * *')).toBe('The 2nd of every month at 9:00 AM')
    expect(describeCron('0 9 3 * *')).toBe('The 3rd of every month at 9:00 AM')
    expect(describeCron('0 9 11 * *')).toBe('The 11th of every month at 9:00 AM')
    expect(describeCron('0 9 21 * *')).toBe('The 21st of every month at 9:00 AM')
    expect(describeCron('0 9 31 * *')).toBe('The 31st of every month at 9:00 AM')
  })

  it('treats a range that covers the whole field as no restriction', () => {
    expect(describeCron('0 9 * * 0-6')).toBe('Daily at 9:00 AM')
    expect(describeCron('0 9 1-31 * *')).toBe('Daily at 9:00 AM')
    expect(describeCron('0 0-23 * * *')).toBe('Every hour')
  })
})

describe('describeCron — declines rather than guesses', () => {
  it('refuses a day-of-month and day-of-week pair, whose meaning is implementation-dependent', () => {
    // Vixie cron ORs them, APScheduler ANDs them, and hub/scheduler.py contains both libraries.
    expect(describeCron('0 9 1 * 1')).toBeNull()
    expect(describeCron('0 0 15 * 5')).toBeNull()
  })

  it('refuses non-standard extensions', () => {
    expect(describeCron('0 9 L * *')).toBeNull()
    expect(describeCron('0 9 ? * MON#1')).toBeNull()
    expect(describeCron('0 9 15W * *')).toBeNull()
    expect(describeCron('0 9 * * MON#2')).toBeNull()
  })

  it('refuses anything that is not five fields', () => {
    expect(describeCron('')).toBeNull()
    expect(describeCron('   ')).toBeNull()
    expect(describeCron('0 9 * *')).toBeNull()
    expect(describeCron('0 0 9 * * *')).toBeNull()
    expect(describeCron('@daily')).toBeNull()
    expect(describeCron('@reboot')).toBeNull()
  })

  it('refuses out-of-range and malformed values', () => {
    expect(describeCron('60 9 * * *')).toBeNull()
    expect(describeCron('0 24 * * *')).toBeNull()
    expect(describeCron('0 9 0 * *')).toBeNull()
    expect(describeCron('0 9 * 13 *')).toBeNull()
    expect(describeCron('0 9 * * 8')).toBeNull()
    expect(describeCron('0 9 * * MOO')).toBeNull()
    expect(describeCron('0 9 * * *,')).toBeNull()
    expect(describeCron('*/0 9 * * *')).toBeNull()
    expect(describeCron('0/1/2 9 * * *')).toBeNull()
  })

  it('refuses a wrapping range instead of picking one reading of it', () => {
    expect(describeCron('0 22-2 * * *')).toBeNull()
  })

  it('refuses sets too large to state exactly', () => {
    // 12 minutes × 9 hours is 108 instants and the minutes do not step across the whole hour, so
    // there is no window phrasing available either.
    expect(describeCron('0,5,10,15,20,25,30,35,40,45,50,55 9,11,13 * * *')).toBeNull()
    // Hours that are neither few enough to list nor evenly spaced.
    expect(describeCron('0 1,2,3,5,8,13 * * *')).toBeNull()
    // Every other day of the month is 16 ordinals, which is a list nobody reads.
    expect(describeCron('0 9 */2 * *')).toBeNull()
  })
})

/**
 * `nextRuns` is computed in UTC on purpose — `hub/scheduler.py` pins its `CronTrigger` to
 * `timezone="UTC"`, so the fields mean UTC wall-clock. These assertions use UTC ISO strings so they
 * hold on any machine's zone; a regression to local getters fails them everywhere except UTC.
 */
describe('nextRuns', () => {
  const iso = (dates: Date[]) => dates.map((d) => d.toISOString())

  it('previews the next three firings of a weekday schedule', () => {
    // 2026-08-24 is a Monday; from Monday 10:00 the next three are Tue/Wed/Thu at 09:00.
    const from = new Date('2026-08-24T10:00:00Z')
    expect(iso(nextRuns('0 9 * * 1-5', from, 3))).toEqual([
      '2026-08-25T09:00:00.000Z',
      '2026-08-26T09:00:00.000Z',
      '2026-08-27T09:00:00.000Z',
    ])
  })

  it('skips the weekend', () => {
    const from = new Date('2026-08-28T10:00:00Z') // Friday, after that day's firing
    expect(iso(nextRuns('0 9 * * 1-5', from, 1))).toEqual(['2026-08-31T09:00:00.000Z'])
  })

  it('returns the same day when the time is still ahead, and never the instant itself', () => {
    expect(iso(nextRuns('0 9 * * *', new Date('2026-08-24T08:59:00Z'), 1))).toEqual([
      '2026-08-24T09:00:00.000Z',
    ])
    // Exactly on the fire time: that firing is now, so the *next* one is tomorrow's.
    expect(iso(nextRuns('0 9 * * *', new Date('2026-08-24T09:00:00Z'), 1))).toEqual([
      '2026-08-25T09:00:00.000Z',
    ])
  })

  it('walks every hour and minute a stepped expression matches, in order', () => {
    const from = new Date('2026-08-24T00:00:00Z')
    expect(iso(nextRuns('*/30 */6 * * *', from, 4))).toEqual([
      '2026-08-24T00:30:00.000Z',
      '2026-08-24T06:00:00.000Z',
      '2026-08-24T06:30:00.000Z',
      '2026-08-24T12:00:00.000Z',
    ])
  })

  it('crosses a month and a year boundary', () => {
    expect(iso(nextRuns('0 0 1 * *', new Date('2026-08-24T00:00:00Z'), 2))).toEqual([
      '2026-09-01T00:00:00.000Z',
      '2026-10-01T00:00:00.000Z',
    ])
    expect(iso(nextRuns('0 0 1 1 *', new Date('2026-08-24T00:00:00Z'), 1))).toEqual([
      '2027-01-01T00:00:00.000Z',
    ])
  })

  it('returns what it has rather than spinning past the scan limit', () => {
    // An annual schedule can only yield one firing inside the ~400-day window.
    expect(nextRuns('0 0 1 1 *', new Date('2026-08-24T00:00:00Z'), 3)).toHaveLength(1)
  })

  it('returns nothing for what describeCron refuses to read', () => {
    expect(nextRuns('0 9 1 * 1', new Date('2026-08-24T00:00:00Z'), 3)).toEqual([])
    expect(nextRuns('@daily', new Date('2026-08-24T00:00:00Z'), 3)).toEqual([])
    expect(nextRuns('nonsense', new Date('2026-08-24T00:00:00Z'), 3)).toEqual([])
    expect(nextRuns('0 9 * * *', new Date('2026-08-24T00:00:00Z'), 0)).toEqual([])
  })
})

describe('formatNextRun', () => {
  const from = new Date('2026-08-24T10:00:00Z') // Monday

  it('names the near days rather than dating them', () => {
    expect(formatNextRun(new Date('2026-08-24T18:00:00Z'), from)).toBe('today 6:00 PM')
    expect(formatNextRun(new Date('2026-08-25T09:00:00Z'), from)).toBe('tomorrow 9:00 AM')
    expect(formatNextRun(new Date('2026-08-27T09:00:00Z'), from)).toBe('Thu 9:00 AM')
    expect(formatNextRun(new Date('2026-08-30T09:00:00Z'), from)).toBe('Sun 9:00 AM')
  })

  it('dates anything a weekday name would no longer locate', () => {
    expect(formatNextRun(new Date('2026-08-31T09:00:00Z'), from)).toBe('Aug 31 9:00 AM')
    expect(formatNextRun(new Date('2026-09-01T00:00:00Z'), from)).toBe('Sep 1 12:00 AM')
  })

  it('reads the preview the mock specified end to end', () => {
    const runs = nextRuns('0 9 * * 1-5', from, 3).map((run) => formatNextRun(run, from))
    expect(runs.join(' · ')).toBe('tomorrow 9:00 AM · Wed 9:00 AM · Thu 9:00 AM')
  })
})
