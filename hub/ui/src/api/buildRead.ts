import { useQueries, useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { BuildRead } from '@/components/builds/buildViewModel'

/** A running build is read again this often as well as on every task and run event, so a missed
 *  event still shows within the 10 seconds the view promises. */
export const BUILD_READ_REFRESH_MS = 6000

/** The key sits under `['project', pid, 'builds']`, which the event stream already invalidates on
 *  every task and run event and on a build starting or stopping. */
export const buildReadKey = (projectId: string | null | undefined, buildId: string) =>
  ['project', projectId, 'builds', 'read', buildId] as const

function readUrl(projectId: string | null | undefined, buildId: string): string {
  return `/api/v1/projects/${projectId}/project/builds/${encodeURIComponent(buildId)}/tasks`
}

/** One build's read (`GET /project/builds/{id}/tasks`): the build view and both summaries draw
 *  from it, so their figures come from the same answer. */
export function useBuildRead(buildId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery({
    queryKey: buildReadKey(projectId, buildId ?? ''),
    queryFn: () => getJson<BuildRead>(readUrl(projectId, buildId ?? '')),
    enabled: isConfigured && !!projectId && !!buildId,
    // Until the first answer says otherwise, the build is taken to be running.
    refetchInterval: (query) => (query.state.data && query.state.data.build.state !== 'running' ? false : BUILD_READ_REFRESH_MS),
    // The last answer stays on screen while the next one is read: nothing jumps.
    placeholderData: (previous) => previous,
  })
}

/** The reads of several builds, by build id, for the compact summaries. A build whose state is
 *  running is read on the same interval; a finished one is read once. */
export function useBuildReads(builds: Array<{ id: string; running: boolean }>): Record<string, BuildRead | undefined> {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const results = useQueries({
    queries: builds.map((build) => ({
      queryKey: buildReadKey(projectId, build.id),
      queryFn: () => getJson<BuildRead>(readUrl(projectId, build.id)),
      enabled: isConfigured && !!projectId,
      refetchInterval: build.running ? BUILD_READ_REFRESH_MS : false,
    })),
  })
  const byId: Record<string, BuildRead | undefined> = {}
  builds.forEach((build, i) => {
    byId[build.id] = results[i]?.data ?? undefined
  })
  return byId
}
