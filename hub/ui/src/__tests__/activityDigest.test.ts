import { describe, it, expect } from 'vitest'
import type { EventLogEntry } from '@/api/logs'
import { buildDigest } from '@/lib/activityDigest'

/** F907: a turn the Hub ends with `run_stopped` or `run_failed` (not only `run_completed`) is one
 *  finished row, not "is working" forever beside a wire-name row. Events are fed in the order the
 *  Hub writes them for a turn. */

let n = 0
const ev = (event_type: string, at: string, data: Record<string, unknown>, severity = 'info'): EventLogEntry => ({
  id: `e${++n}`,
  project_id: 'p',
  event_type,
  agent: 'alpha',
  data: { agent: 'alpha', ...data },
  severity,
  timestamp: at,
})

function turn(ending: EventLogEntry): EventLogEntry[] {
  return [
    ev('queue_entry_queued', '2026-10-22T09:25:00Z', { entry_id: 'q1' }),
    ev('run_triggered', '2026-10-22T09:25:01Z', { run_id: 'run-1' }),
    ev('queue_entry_delivered', '2026-10-22T09:25:02Z', { run_id: 'run-1', entry_id: 'q1' }),
    ev('run_started', '2026-10-22T09:25:03Z', { run_id: 'run-1' }),
    ev('context_warning', '2026-10-22T09:25:30Z', { run_id: 'run-1' }),
    ending,
  ]
}

const rowsOf = (events: EventLogEntry[]) => buildDigest(events).flatMap((d) => d.rows)

describe('a turn ended by run_stopped / run_failed', () => {
  it('run_stopped joins its run: one row, not "is working", with the duration', () => {
    const rows = rowsOf(turn(ev('run_stopped', '2026-10-22T09:25:33Z', { run_id: 'run-1', exit_code: 2 })))
    expect(rows).toHaveLength(1)
    expect(rows[0]!.kind).toBe('turn')
    expect(rows[0]!.text).toBe('was stopped')
    expect(rows[0]!.severity).toBe('warn')
    expect(rows[0]!.durationSeconds).toBe(30)
    expect(rows.some((r) => r.text === 'run stopped')).toBe(false)
  })

  it('run_failed joins its run: one row, an error, no "run failed" row', () => {
    const rows = rowsOf(turn(ev('run_failed', '2026-10-22T09:26:03Z', { run_id: 'run-1', exit_code: 1 }, 'warn')))
    expect(rows).toHaveLength(1)
    expect(rows[0]!.kind).toBe('turn')
    expect(rows[0]!.text).toBe('stopped with an error')
    expect(rows[0]!.severity).toBe('error')
    expect(rows[0]!.durationSeconds).toBe(60)
    expect(rows.some((r) => r.text === 'run failed')).toBe(false)
  })

  it('a completed turn still reads "worked", and a running one "is working"', () => {
    const done = rowsOf(turn(ev('run_completed', '2026-10-22T09:25:40Z', { run_id: 'run-1', exit_code: 0 })))
    expect(done.map((r) => r.text)).toEqual(['worked'])
    const running = rowsOf(turn(ev('context_warning', '2026-10-22T09:25:31Z', { run_id: 'run-1' })))
    expect(running.map((r) => r.text)).toEqual(['is working'])
  })
})
