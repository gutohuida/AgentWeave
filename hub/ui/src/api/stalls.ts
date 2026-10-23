import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'

/** One time the project's work stopped moving (`hub/hub/stalls.py`). */
export interface Stall {
  id: string
  key: string
  cause:
    | 'loop_stalled'
    | 'delivery_refused'
    | 'integration_skipped'
    | 'integration_failed'
    | 'review_unstaffed'
    | 'dead_run'
    | 'stuck_task'
    | 'no_progress'
  reason: string
  task_id: string | null
  loop_id: string | null
  first_seen_at: string
  last_seen_at: string
  seen_count: number
  /** The mender's thread for this stall; null while the mender is off or could not be woken. */
  conversation_id: string | null
  mender_turns: number
  outcome: 'open' | 'fixed' | 'gave_up' | 'resolved'
  outcome_detail: string
  ended_at: string | null
}

/** The project's open stalls, newest first. SSE (`stall_recorded`, `stall_ended`) invalidates it. */
export function useOpenStalls() {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<Stall[]>({
    queryKey: ['project', projectId, 'stalls', 'open'],
    queryFn: async () =>
      (await getJson<{ stalls: Stall[] }>(`/api/v1/projects/${projectId}/stalls?open=true`)).stalls,
    enabled: isConfigured && !!projectId,
  })
}

/** End an open stall by hand (`POST /stalls/{id}/end`, outcome `resolved`). */
export function useEndStall() {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (stallId: string) =>
      postJson<Stall>(`/api/v1/projects/${projectId}/stalls/${stallId}/end`, {
        outcome: 'resolved',
        detail: 'Dismissed by the operator.',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project', projectId, 'stalls'] }),
  })
}
