import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface PermissionRequest {
  id: string
  agent: string
  run_id: string | null
  tool_name: string
  tool_use_id: string
  tool_input: Record<string, unknown>
  status: 'pending' | 'allowed' | 'denied' | 'expired'
  created_at: string
  decided_at: string | null
  decided_by: string | null
}

/** Permission requests waiting on the operator.
 *
 * A run blocks while one of these is pending and gives up after its own timeout, so this
 * refetches on a short interval as well as on SSE: arriving late is the same as not arriving,
 * and a dropped event would leave an agent waiting for a card that never appeared.
 */
export function usePendingPermissionRequests() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { project_id?: string }
    if (
      (event.type === 'permission_requested' || event.type === 'permission_decided') &&
      d.project_id === projectId
    ) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'permission-requests'] })
    }
  })

  return useQuery<PermissionRequest[]>({
    queryKey: ['project', projectId, 'permission-requests'],
    queryFn: () =>
      getJson<PermissionRequest[]>(`/api/v1/projects/${projectId}/permission-requests`),
    enabled: isConfigured && !!projectId,
    refetchInterval: 3000,
  })
}

export function useDecidePermissionRequest() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: ({ id, allow }: { id: string; allow: boolean }) =>
      postJson(`/api/v1/projects/${projectId}/permission-requests/${id}/decide`, { allow }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'permission-requests'] })
    },
  })
}
