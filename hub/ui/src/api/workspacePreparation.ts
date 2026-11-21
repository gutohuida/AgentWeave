import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** A checkout the Hub is preparing for a turn right now (`GET /workspace/preparing`). */
export interface WorkspacePreparation {
  id: string
  agent: string
  task_id: string | null
  conversation_id: string | null
  started_at: string
}

/** Live: `workspace_preparing` and `workspace_prepared` invalidate it (`useSSE`). */
export function usePreparingWorkspaces() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<WorkspacePreparation[]>({
    queryKey: ['project', projectId, 'preparing'],
    queryFn: () => getJson<WorkspacePreparation[]>(`/api/v1/projects/${projectId}/workspace/preparing`),
    enabled: isConfigured && !!projectId,
  })
}
