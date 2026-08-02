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
  const { isConfigured } = useConfigStore()
  const queryClient = useQueryClient()

  useSSE((event) => {
    const d = (event.data ?? {}) as { agent?: string }
    if (agent && d.agent === agent) {
      queryClient.invalidateQueries({ queryKey: ['queue', agent, 'status'] })
    }
    if (agent && (event.type === 'run_started' || event.type === 'run_completed'
      || event.type === 'run_failed' || event.type === 'run_stopped'
      || event.type === 'run_interrupted') && d.agent === agent) {
      queryClient.invalidateQueries({ queryKey: ['queue', agent, 'status'] })
    }
  })

  return useQuery<QueueStatus>({
    queryKey: ['queue', agent, 'status'],
    queryFn: () => getJson<QueueStatus>(`/api/v1/queue/${agent}/status`),
    enabled: isConfigured && !!agent,
  })
}

/** Withdraws an undelivered queue entry (spec: "Undelivered entries can be
 * withdrawn"). The Phase 6 endpoint already enforces "not yet delivered". */
export async function withdrawQueueEntry(entryId: string): Promise<void> {
  await fetchWithAuth(`/api/v1/queue/entries/${entryId}`, { method: 'DELETE' })
}
