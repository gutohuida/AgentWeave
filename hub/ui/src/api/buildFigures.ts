import { useQueries } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { SpecBuild } from './spec'

/** What a build has taken so far (`GET /project/builds/{id}/figures`): the runs bound to its tasks,
 *  the wall time split by what the build was doing (seconds) and the cost split by who spent it
 *  (dollars). This is the one place the spec page's figures come from: roadmap slice G replaces the
 *  Hub module behind this route and, with it, the body of this hook. */
export interface BuildFigures {
  id: string
  runs: number
  time: { building: number; checks: number; review: number; waiting: number }
  cost: { build: number; review: number; lead: number }
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
