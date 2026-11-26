import { useQueries, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
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

/** Each task's stage and check state, as one comparable line. */
function stagesOf(read: BuildRead | undefined): Map<string, string> {
  return new Map((read?.tasks ?? []).map((task) => [task.id, JSON.stringify([task.stage ?? null, task.check_state ?? null])]))
}

/** Read one build; where the answer moves a task's stage or check state past the one cached, the
 *  task list is refetched too. The board and the map read that list, and a move announces nothing
 *  when it is the read's own poll that found it (Landing checks -> Landing, drive run 132112), so
 *  without this the build view showed Landing while the other two still said Landing checks
 *  (`same-stage-everywhere`). */
async function readBuild(queryClient: QueryClient, projectId: string | null | undefined, buildId: string): Promise<BuildRead> {
  const read = await getJson<BuildRead>(readUrl(projectId, buildId), { first: true })
  const before = queryClient.getQueryData<BuildRead>(buildReadKey(projectId, buildId))
  if (before) {
    const was = stagesOf(before)
    if ([...stagesOf(read)].some(([id, now]) => was.has(id) && was.get(id) !== now)) {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'tasks'] })
    }
  }
  return read
}

/** One build's read (`GET /project/builds/{id}/tasks`): the build view and both summaries draw
 *  from it, so their figures come from the same answer. */
export function useBuildRead(buildId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()
  return useQuery({
    queryKey: buildReadKey(projectId, buildId ?? ''),
    queryFn: () => readBuild(queryClient, projectId, buildId ?? ''),
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
  const queryClient = useQueryClient()
  const results = useQueries({
    queries: builds.map((build) => ({
      queryKey: buildReadKey(projectId, build.id),
      queryFn: () => readBuild(queryClient, projectId, build.id),
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
