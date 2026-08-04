import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, fetchWithAuth } from './client'
import { useConfigStore } from '@/store/configStore'
import { useSSE } from '@/hooks/useSSE'

export interface QueueStatus {
  agent: string
  waiting_count: number
  running: boolean
  waiting_reason: string | null
}

/** Backs task 8.6 (waiting-entry count + the reason an agent isn't running) —
 * both fields already computed server-side by the Phase 6 queue endpoint, so
 * this is a thin read hook, not new logic. */
export function useQueueStatus(agent: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { agent?: string; project_id?: string }
    if (d.project_id !== projectId || !agent || d.agent !== agent) return
    if (
      event.type === 'run_started' || event.type === 'run_completed'
      || event.type === 'run_failed' || event.type === 'run_stopped'
      || event.type === 'run_interrupted'
      || event.type === 'queue_entry_queued' || event.type === 'queue_entry_delivered'
      || event.type === 'queue_entry_withdrawn' || event.type === 'queue_chain_suspended'
    ) {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'queue', agent, 'status'] })
    }
  })

  return useQuery<QueueStatus>({
    queryKey: ['project', projectId, 'queue', agent, 'status'],
    queryFn: () => getJson<QueueStatus>(`/api/v1/projects/${projectId}/queue/${agent}/status`),
    enabled: isConfigured && !!projectId && !!agent,
  })
}

/** Withdraws an undelivered queue entry (spec: "Undelivered entries can be
 * withdrawn"). The Phase 6 endpoint already enforces "not yet delivered". */
export async function withdrawQueueEntry(projectId: string, entryId: string): Promise<void> {
  await fetchWithAuth(`/api/v1/projects/${projectId}/queue/entries/${entryId}`, {
    method: 'DELETE',
  })
}
