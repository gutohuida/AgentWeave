import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { LoopSummary } from './jobs'

export type { LoopSummary }

/** A loop's own record (`GET /projects/{project_id}/loops/{loop_id}`) — everything `LoopSummary`
 *  carries, plus the parent job id and its firing history. Readable regardless of `archived_at`
 *  (design D16): the drill-down tab is the governance record, most valuable once a loop has
 *  already ended (task B6.5). */
export interface LoopDetail extends LoopSummary {
  job_id: string
  history: Array<{
    id: string
    job_id: string
    fired_at: string
    status: string
    trigger: string
    session_id?: string
  }>
  /** This loop's own audit trail (design D13, task A4.1/A4.2) — control changes, staged and
   *  applied edits, how it stopped. Filtered server-side by loop id; never another loop's rows. */
  events: Array<{
    id: string
    event_type: string
    agent?: string | null
    data: Record<string, unknown>
    timestamp: string
  }>
}

/** Project-scoped loop listing (design D20, task B4.3) — no conversation id, because a loop
 *  firing always starts a fresh conversation, so a conversation-scoped view would be empty in
 *  every conversation the operator actually sits in. Archived loops are excluded unless asked
 *  for (task B5.4), mirroring `useJobs`'s own `include_archived` shape. */
export function useLoops(includeArchived = false) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<LoopSummary[]>({
    queryKey: ['project', projectId, 'loops', { includeArchived }],
    queryFn: () =>
      getJson<LoopSummary[]>(
        `/api/v1/projects/${projectId}/loops?include_archived=${includeArchived}`,
      ),
    enabled: isConfigured && !!projectId,
  })
}

export function useLoop(loopId: string | null) {
  const { isConfigured, selectedProjectId: projectId } = useConfigStore()
  return useQuery<LoopDetail>({
    queryKey: ['project', projectId, 'loops', loopId],
    queryFn: () => getJson<LoopDetail>(`/api/v1/projects/${projectId}/loops/${loopId}`),
    enabled: isConfigured && !!projectId && !!loopId,
  })
}
