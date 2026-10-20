import type { Job } from '@/api/jobs'
import { loopEnded, loopPastStop } from '@/components/spec/loopCounts'

/** What a job's row says it is. A loop that has ended is `finished`, whatever its `enabled` flag:
 *  the Hub refuses to enable it again (409 loop_ended), so the row must not offer a switch. */
export function jobState(job: Job): 'active' | 'paused' | 'finished' {
  if (job.loop?.ending_state) return 'finished'
  return job.enabled ? 'active' : 'paused'
}

/** A loop's own state in a word, which outranks `enabled` (F714): an ended loop is Complete or
 *  Stopped, one past its stop time is Stopping (F655). Null for a plain job. */
export function loopStateLabel(job: Job): 'Complete' | 'Stopped' | 'Stopping' | 'Active' | null {
  const loop = job.loop
  if (!loop) return null
  if (loopEnded(loop)) return loop.ending_state === 'completed' ? 'Complete' : 'Stopped'
  if (loopPastStop(loop)) return 'Stopping'
  return 'Active'
}

/** One status→colour map for a job run, read by the history rows and the trend dots alike. */
export function runStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'var(--green)'
    case 'failed':
      return 'var(--red)'
    case 'skipped':
      return 'var(--amber)'
    default:
      return 'var(--text-3)'
  }
}
