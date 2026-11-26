import * as React from 'react'
import { useArchivedJobs, useJobs } from '@/api/jobs'
import { useLoops } from '@/api/loops'
import { useProjectBuilds } from '@/api/projectBuilds'
import { useBuildReads } from '@/api/buildRead'
import { needsLine, summaryOf, type BuildSummaryModel } from '@/components/builds/buildViewModel'
import { runningItems, type RunningItem } from './runningModel'

/** Builds whose summary is read: the newest, so a long history does not read every old build. */
const SUMMARISED_BUILDS = 30

/** How often the relative times ("started 4m ago", "next in 2m") are re-worded without a refetch. */
const CLOCK_MS = 30_000

/** The items Running lists, from the Hub's three reads: builds, loops and jobs. Live: each read is a
 *  query the app's event-driven invalidation already refreshes (`useSSE`). Shared by the tab and by
 *  the launcher's count so the two cannot disagree. */
export function useRunningItems(): {
  items: RunningItem[]
  isLoading: boolean
  loadFailed: boolean
  /** Each build's compact summary, by build id, from the build view's read. */
  buildSummaries: Record<string, BuildSummaryModel | undefined>
} {
  const { data: builds = [], isLoading: buildsLoading, error: buildsError } = useProjectBuilds()
  // Archived loops and jobs included: they are what Finished lists for plain work.
  const { data: loops = [], isLoading: loopsLoading, error: loopsError } = useLoops(true, { stages: true })
  const { data: jobs = [], isLoading: jobsLoading, error: jobsError } = useJobs()
  const { data: archivedJobs = [], error: archivedError } = useArchivedJobs()
  const [now, setNow] = React.useState(() => new Date())
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), CLOCK_MS)
    return () => window.clearInterval(timer)
  }, [])
  const reads = useBuildReads(builds.slice(0, SUMMARISED_BUILDS).map((b) => ({ id: b.id, running: b.state === 'running' })))
  const { buildSummaries, buildNeeds } = React.useMemo(() => {
    const summaries: Record<string, BuildSummaryModel | undefined> = {}
    const needs: Record<string, string | null> = {}
    for (const [id, read] of Object.entries(reads)) {
      if (!read) continue
      summaries[id] = summaryOf(read, now)
      needs[id] = needsLine(read)
    }
    return { buildSummaries: summaries, buildNeeds: needs }
  }, [reads, now])
  const items = React.useMemo(
    () =>
      runningItems({
        builds,
        loops,
        jobs: [...jobs, ...archivedJobs.filter((a) => !jobs.some((j) => j.id === a.id))],
        now,
        buildNeeds,
      }),
    [builds, loops, jobs, archivedJobs, now, buildNeeds],
  )
  const loadFailed = Boolean(buildsError || loopsError || jobsError || archivedError)
  return { items, isLoading: buildsLoading || loopsLoading || jobsLoading, loadFailed, buildSummaries }
}

/** What the launcher card counts: the items that need the operator or are working. */
export function runningCount(items: RunningItem[]): number {
  return items.filter((i) => i.phase === 'needs-you' || i.phase === 'working').length
}
