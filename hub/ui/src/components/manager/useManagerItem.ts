import * as React from 'react'
import {
  useMarkManagerRunsSeen,
  useRunningManagerRuns,
  useUnseenManagerFailures,
  type ManagerEndedRun,
  type ManagerUnseenFailure,
} from '@/api/manager'
import { useSSE, type SSEEvent } from '@/hooks/useSSE'
import { useConfigStore } from '@/store/configStore'
import { onItem } from './managerRuns'

export type ManagerIconState = 'idle' | 'working' | 'failed'

/** How long a press shows "working" while waiting for its run's start to arrive. A run that never
 *  starts (the job turned off between the press and its answer) stops pretending after this. */
const STARTING_MS = 20_000

/**
 * The manager's state on one item (`background-manager-work-you-can-see`, FR-4 to FR-6): working
 * while a run of *job* on it is in progress, failed while its newest run failed unseen, else idle.
 *
 * - `matches` narrows the job's runs to this item by subject (a spec's `document`); without it
 *   every run of the job is this item's (the Vault page and distillation).
 * - `onEnded` is called when a run on the item ends, so the placement re-reads its product (FR-5).
 * - `seeOnShow`: the placement is the item's warning or failure list, so showing a failure is the
 *   operator seeing it, and it is marked seen at once (FR-6). The icon keeps showing it failed in
 *   this view until a run on the item starts, so the operator sees what they arrived to.
 * - `starting()` is for the placement's own control (Check now): the icon goes straight to working,
 *   with no idle between a failure and the run's start arriving.
 */
export function useManagerItem({
  job,
  matches,
  onEnded,
  seeOnShow = false,
}: {
  job: string
  matches?: (subject: Record<string, unknown>) => boolean
  onEnded?: (run: ManagerEndedRun) => void
  seeOnShow?: boolean
}) {
  const projectId = useConfigStore((state) => state.selectedProjectId)
  const running = useRunningManagerRuns()
  const unseen = useUnseenManagerFailures()
  const markSeen = useMarkManagerRunsSeen()
  const [startingSince, setStartingSince] = React.useState<number | null>(null)
  const [shownFailure, setShownFailure] = React.useState<ManagerUnseenFailure | null>(null)
  const matchesRef = React.useRef(matches)
  matchesRef.current = matches
  const onEndedRef = React.useRef(onEnded)
  onEndedRef.current = onEnded

  // Failures a later run on the item replaced: the Hub stops listing them, but a re-read in flight
  // may still carry one, and it must not bring the failed state back.
  const superseded = React.useRef(new Set<string>())
  const runs = (running.data ?? []).filter((run) => onItem(run, job, matches))
  const failures = (unseen.data ?? []).filter(
    (failure) => onItem(failure, job, matches) && !superseded.current.has(failure.run_id),
  )
  const isRunning = runs.length > 0
  const failureIds = failures.map((f) => f.run_id).join(',')
  const supersede = React.useCallback(() => {
    failureIds.split(',').forEach((id) => id && superseded.current.add(id))
    setShownFailure(null)
  }, [failureIds])
  const supersedeRef = React.useRef(supersede)
  supersedeRef.current = supersede

  useSSE((event: SSEEvent) => {
    if (event.type !== 'manager_run_started' && event.type !== 'manager_run_ended') return
    const run = event.data as (ManagerEndedRun & { project_id?: string }) | null
    if (!run || (run.project_id && run.project_id !== projectId)) return
    if (!onItem(run, job, matchesRef.current)) return
    if (event.type === 'manager_run_started') {
      supersedeRef.current()
      setStartingSince(null)
    } else {
      setStartingSince(null)
      onEndedRef.current?.(run)
    }
  })

  // The run arrived in the running list: it, not the press, says working from here.
  React.useEffect(() => {
    if (isRunning) {
      setStartingSince(null)
      supersedeRef.current()
    }
  }, [isRunning])

  React.useEffect(() => {
    if (startingSince === null) return
    const timer = setTimeout(() => setStartingSince(null), STARTING_MS)
    return () => clearTimeout(timer)
  }, [startingSince])

  const newest = failures[failures.length - 1] ?? null
  const { mutate: see } = markSeen
  const posted = React.useRef(new Set<string>())
  React.useEffect(() => {
    if (!newest || startingSince !== null || isRunning) return
    setShownFailure((shown) => shown ?? newest)
    if (!seeOnShow) return
    const fresh = failureIds.split(',').filter((id) => id && !posted.current.has(id))
    if (!fresh.length) return
    fresh.forEach((id) => posted.current.add(id))
    see(fresh)
  }, [failureIds, newest, seeOnShow, see, startingSince, isRunning])

  const state: ManagerIconState =
    isRunning || startingSince !== null ? 'working' : failures.length > 0 || shownFailure ? 'failed' : 'idle'

  /** Mark this item's listed failures seen (a placement whose failure list opens on demand). */
  const seeFailures = React.useCallback(() => {
    const fresh = failureIds.split(',').filter((id) => id && !posted.current.has(id))
    if (!fresh.length) return
    fresh.forEach((id) => posted.current.add(id))
    see(fresh)
  }, [failureIds, see])

  // What a press set aside, so a press the Hub refused gives the failure back.
  const pressed = React.useRef<{ ids: string[]; shown: ManagerUnseenFailure | null }>({ ids: [], shown: null })
  const starting = React.useCallback(() => {
    pressed.current = { ids: failureIds.split(',').filter(Boolean), shown: shownFailure }
    supersede()
    setStartingSince(Date.now())
  }, [supersede, failureIds, shownFailure])
  const cancelStarting = React.useCallback(() => {
    pressed.current.ids.forEach((id) => superseded.current.delete(id))
    setShownFailure(pressed.current.shown)
    pressed.current = { ids: [], shown: null }
    setStartingSince(null)
  }, [])

  // Ready once both reads have answered (or will not): until then the state could read idle for a
  // failure that is on its way.
  const ready =
    (running.data !== undefined || running.error != null || running.fetchStatus === 'idle') &&
    (unseen.data !== undefined || unseen.error != null || unseen.fetchStatus === 'idle')

  return {
    state,
    ready,
    runs,
    failure: failures[failures.length - 1] ?? shownFailure,
    failures: failures.length ? failures : shownFailure ? [shownFailure] : [],
    starting,
    cancelStarting,
    seeFailures,
  }
}
