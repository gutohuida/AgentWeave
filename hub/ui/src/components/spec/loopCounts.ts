import type { LoopSummary } from '@/api/loops'
import { hubDate } from '@/lib/hubTime'

/** Whether the loop has ended — completed, or stopped by the operator or its stop condition. An
 *  ended loop's job is disabled for good: resuming it is refused (`loop_ended`), so no surface may
 *  read it as merely paused (F714). */
export function loopEnded(loop: LoopSummary): boolean {
  return Boolean(loop.ending_state || loop.stop_reason)
}

/** A loop past its stop time that the scheduler has not yet recorded as stopped (F655): the next
 *  tick stops it without firing, so it is neither active nor due to run again. Shared so the Jobs
 *  card and the loop's own tab say the same word for it (F714). */
export function loopPastStop(loop: LoopSummary): boolean {
  return Boolean(
    !loopEnded(loop) && loop.stop_at && hubDate(loop.stop_at).getTime() <= Date.now(),
  )
}

export type EndingBucket = 'running' | 'stalled' | 'idle' | 'completed' | 'stopped'

/** B5.3: counts by *ending state*, never by matching `stop_reason` text — `ending_state` is the
 *  one value design D17 says is authoritative for what happened to a loop. Nothing here re-derives
 *  that from the presence/absence of a `stop_reason` string.
 *
 *  `ending_state === null` means the loop has never *ended*, which is not the same as running: a
 *  loop whose job is paused, or which has simply not reached its next firing, has no ending state
 *  either. Treating null as "running" reported a paused loop that had never fired once as running.
 *  `firing_active` is the live fact — computed Hub-side from a `JobRun` in progress with a running
 *  `Run` (`loops.py`, task A4.4) — and is what separates the two.
 *
 *  Known limitation, stated rather than guessed at: `idle` cannot yet distinguish "paused" from
 *  "waiting for its next firing", because `LoopSummary` does not carry the parent job's `enabled`.
 *  Adding it there is what would let this say which. */
export function endingBucket(loop: LoopSummary): EndingBucket {
  // `loop-notices-and-reacts` 5.5. A stalled loop used to fall through to `idle`, which is the one
  // reading it must not have: it is waiting on something nameable, and "idle" says both that
  // nothing is happening and that nothing is wrong. `stall_reason` is set exactly when the next
  // firing would be refused, by the same computation that would refuse it.
  if (!loop.stopped_at && !loop.ending_state && loop.stall_reason) return 'stalled'
  if (loop.ending_state === 'completed') return 'completed'
  if (loop.ending_state === 'stopped') return 'stopped'
  return loop.firing_active ? 'running' : 'idle'
}
