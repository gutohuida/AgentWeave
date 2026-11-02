import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A follow-up reopened a finished build (`hub/hub/builds.py`, `reopening_warnings`). It stands until
 *  the operator dismisses it or the build ends. */
export interface ReopeningWarning {
  build_id: string
  document_id: string
  path: string
  title: string
  reopened_at: string
  finished_at: string
  /** How long before the reopening the build had finished, in words: `30 days`. */
  finished_ago: string
  tasks: { id: string; display_id: string; title: string; filer: string }[]
}

/** Newest first, as the route answers. SSE (`build_updated`, `build_stopped`) invalidates it. */
export function useReopeningWarnings() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<ReopeningWarning[]>({
    queryKey: ['project', projectId, 'reopeningWarnings'],
    queryFn: async () =>
      (await getJson<{ warnings: ReopeningWarning[] }>(`/api/v1/projects/${projectId}/project/reopening-warnings`)).warnings,
    enabled: isConfigured && !!projectId,
  })
}

/** Stop the reopened build: nothing new is handed out. */
export function useStopReopenedBuild() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (buildId: string) => postJson(`/api/v1/projects/${projectId}/project/builds/${buildId}/stop`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'reopeningWarnings'] }),
  })
}

/** Let it run: the warning goes, the build does not. */
export function useDismissReopeningWarning() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (buildId: string) => postJson(`/api/v1/projects/${projectId}/project/builds/${buildId}/reopening-warning/dismiss`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'reopeningWarnings'] }),
  })
}
