import type { LoopSummary } from '@/api/loops'

export type EndingBucket = 'running' | 'completed' | 'stopped'

/** B5.3: counts by *ending state*, never by matching `stop_reason` text — `ending_state` is the
 *  one value design D17 says is authoritative for what happened to a loop. `null` means still
 *  running; nothing here re-derives that from the presence/absence of a `stop_reason` string. */
export function endingBucket(loop: LoopSummary): EndingBucket {
  if (loop.ending_state === 'completed') return 'completed'
  if (loop.ending_state === 'stopped') return 'stopped'
  return 'running'
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
