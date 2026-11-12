import * as React from 'react'
import { useArchivedJobs, useJobs } from '@/api/jobs'
import { useLoops } from '@/api/loops'
import { useProjectBuilds } from '@/api/projectBuilds'
import { runningItems, type RunningItem } from './runningModel'

/** How often the relative times ("started 4m ago", "next in 2m") are re-worded without a refetch. */
const CLOCK_MS = 30_000

/** The items Running lists, from the Hub's three reads: builds, loops and jobs. Live: each read is a
 *  query the app's event-driven invalidation already refreshes (`useSSE`). Shared by the tab and by
 *  the launcher's count so the two cannot disagree. */
export function useRunningItems(): { items: RunningItem[]; isLoading: boolean } {
  const { data: builds = [], isLoading: buildsLoading } = useProjectBuilds()
  // Archived loops and jobs included: they are what Finished lists for plain work.
  const { data: loops = [], isLoading: loopsLoading } = useLoops(true)
  const { data: jobs = [], isLoading: jobsLoading } = useJobs()
  const { data: archivedJobs = [] } = useArchivedJobs()
  const [now, setNow] = React.useState(() => new Date())
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), CLOCK_MS)
    return () => window.clearInterval(timer)
  }, [])
  const items = React.useMemo(
    () => runningItems({ builds, loops, jobs: [...jobs, ...archivedJobs.filter((a) => !jobs.some((j) => j.id === a.id))], now }),
    [builds, loops, jobs, archivedJobs, now],
  )
  return { items, isLoading: buildsLoading || loopsLoading || jobsLoading }
}

/** What the launcher card counts: the items that need the operator or are working. */
export function runningCount(items: RunningItem[]): number {
  return items.filter((i) => i.phase === 'needs-you' || i.phase === 'working').length
}
