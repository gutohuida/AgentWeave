import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJson, patchJson, postJson } from './client'
import { useConfigStore } from '@/store/configStore'
import type { Job, JobCreate, JobUpdate, LoopSummary } from './jobs'

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

/** Every loop action re-reads the loops and the jobs on *settle*, not on success: a Stop that lost
 *  a race with another tab or a firing is refused with 409, and the tab must then show what the
 *  Hub recorded rather than keep offering a control that no longer applies. */
function useLoopMutation<TVars>(mutationFn: (projectId: string | null, vars: TVars) => Promise<unknown>) {
  const queryClient = useQueryClient()
  const { selectedProjectId: projectId } = useConfigStore()
  return useMutation({
    mutationFn: (vars: TVars) => mutationFn(projectId, vars),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'loops'] })
      queryClient.invalidateQueries({ queryKey: ['project', projectId, 'jobs'] })
    },
  })
}

/** The operator stop — the existing `PATCH /jobs/{id}` with `stop_reason`, not a second route
 *  (design D2). Sends `stop_reason` alone: no `enabled`, see the change's *Residuals*. */
export function useStopLoop() {
  return useLoopMutation<{ jobId: string; reason: string }>((projectId, { jobId, reason }) =>
    patchJson(`/api/v1/projects/${projectId}/jobs/${jobId}`, { stop_reason: reason }),
  )
}

export function useArchiveLoop() {
  return useLoopMutation<{ loopId: string }>((projectId, { loopId }) =>
    postJson(`/api/v1/projects/${projectId}/loops/${loopId}/archive`),
  )
}

export function useSetLoopControl() {
  return useLoopMutation<{ loopId: string; control: 'creator' | 'operator' }>(
    (projectId, { loopId, control }) =>
      postJson(`/api/v1/projects/${projectId}/loops/${loopId}/control`, { control }),
  )
}

/** The operator's settings edit — `PATCH /jobs/{id}`, sending only the fields that changed. On a
 *  loop the Hub stages the loop's fields and the agent for the next firing and applies name,
 *  message and cadence at once, so both the loops and the jobs are re-read on settle. */
export function useUpdateLoopSettings(jobId: string | null) {
  return useLoopMutation<JobUpdate>((projectId, updates) =>
    patchJson<Job>(`/api/v1/projects/${projectId}/jobs/${jobId}`, updates),
  )
}

/** Starts a flow: `POST /jobs` with a `spec_document_id`. Invalidates the loops as well as the
 *  jobs (`useCreateJob` does only the jobs), or the document page would keep offering to start a
 *  flow that now exists and a second press would answer 409. */
export function useCreateFlow() {
  return useLoopMutation<JobCreate>((projectId, job) =>
    postJson<Job>(`/api/v1/projects/${projectId}/jobs`, job),
  )
}

/** The unarchived loop that declares this document, if any. The route orders by creation and the
 *  partial unique index allows at most one unarchived loop per document, so order does not matter. */
export function useDocumentFlow(documentId: string | null | undefined): LoopSummary | undefined {
  const { data } = useLoops()
  if (!documentId) return undefined
  return data?.find((loop) => loop.spec_document_id === documentId)
}
