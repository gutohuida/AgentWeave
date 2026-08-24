import type { LoopSummary } from '@/api/loops'

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

/** How many loops are running right now. Its own module rather than an export from
 *  `LoopsIndexTab` because two unrelated surfaces need it — the index's own summary line and the
 *  panel shell's launcher badge, one screen earlier — and a second hand-rolled count is exactly
 *  how three copies of a status mapping drifted apart before.
 *
 *  An archived loop is excluded: archiving is a governance act on a loop that has stopped, so
 *  counting one as running would be a contradiction the badge cannot explain. */
export function runningLoopCount(loops: LoopSummary[]): number {
  return loops.filter((loop) => !loop.archived_at && endingBucket(loop) === 'running').length
}
