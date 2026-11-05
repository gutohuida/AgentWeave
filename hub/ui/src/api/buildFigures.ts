import { useQueries } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { SpecBuild } from './spec'

/** What a build has taken so far (`GET /project/builds/{id}/figures`): its runs, the wall time split
 *  by what the build was doing (seconds, parts that sum to the span) and the cost split by who spent
 *  it (dollars; null where runs ran and none reported a cost). It is the work tally's row for the
 *  build (`GET /stats` carries the same rows), so the card and the project view cannot disagree. */
export interface BuildFigures {
  id: string
  runs: number
  time: { building: number; reviewing: number; checks: number; held: number; review: number; waiting: number }
  cost: { build: number | null; review: number | null; lead: number | null; mend: number | null }
  /** Runs counted beside the cost: no cost was reported for them. */
  unpriced: number
  checks: BuildChecks
  /** Time from a task's last approval to its landing on main. */
  landing?: BuildLanding
}

/** The build's check runs. `waiting_seconds` is null when no run has a recorded slot time. */
export interface BuildChecks {
  runs: number
  passed: number
  failed: number
  seconds: number
  timed_out?: number
  running_seconds?: number
  waiting_seconds?: number | null
  no_slot_runs?: number
}

export interface BuildLanding {
  landed: number
  total_seconds: number
  longest_seconds: number
  waiting: number
  longest_waiting_seconds: number
}

const LIVE_REFRESH_MS = 5000

/** The figures of each build, by build id. A running build is read again every few seconds (its
 *  numbers move as it works); a finished one is read once. */
export function useBuildFigures(builds: SpecBuild[]): Record<string, BuildFigures | undefined> {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const results = useQueries({
    queries: builds.map((build) => ({
      queryKey: ['project', projectId, 'buildFigures', build.id],
      queryFn: () => getJson<BuildFigures>(`/api/v1/projects/${projectId}/project/builds/${build.id}/figures`),
      enabled: isConfigured && !!projectId,
      refetchInterval: build.state === 'running' ? LIVE_REFRESH_MS : false,
    })),
  })
  const byId: Record<string, BuildFigures | undefined> = {}
  builds.forEach((build, i) => {
    byId[build.id] = results[i]?.data ?? undefined
  })
  return byId
}
